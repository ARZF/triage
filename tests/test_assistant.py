import asyncio
from contextlib import closing
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agent import doctor_assistant as bridge
from app.core import db
from app.core.config import Settings
from app.core.errors import ServiceError
from app.main import app
from app.schemas.assistant import AssistantRequest
from helpers import admin_account, register_doctor, register_patient


def event(method, **params):
    return {"method": method, "params": params}


def final_events(text="پاسخ ساختگی"):
    return [event("item/started", item={"id": "answer", "type": "agentMessage", "phase": "final_answer"}),
            event("item/agentMessage/delta", itemId="answer", delta=text),
            event("item/completed", item={"id": "answer", "type": "agentMessage", "phase": "final_answer", "text": text}),
            event("turn/completed", turn={"id": "turn", "status": "completed"})]


class RecordingInput(io.BytesIO):
    def close(self):
        self.was_closed = True


class FakeProcess:
    def __init__(self, notifications=(), thread=None, early=()):
        replies = [{"id": 1, "result": {}}, {"id": 2, "result": {"account": {"type": "chatgpt"}}},
                   {"id": 3, "result": {"thread": thread or {"id": "thread", "ephemeral": True},
                                         "instructionSources": [], "runtimeWorkspaceRoots": []}},
                   *early, {"id": 4, "result": {"turn": {"id": "turn"}}}, *notifications]
        self.stdin = RecordingInput()
        self.stdout = io.BytesIO(b"".join((json.dumps(value) + "\n").encode() for value in replies))
        self.returncode = None
        self.terminated = self.killed = False
        self.waits = 0

    def poll(self): return self.returncode
    def terminate(self): self.terminated = True; self.returncode = 0
    def kill(self): self.killed = True; self.returncode = -9
    def wait(self, timeout=None): self.waits += 1; return self.returncode
    def sent(self): return [json.loads(line) for line in self.stdin.getvalue().splitlines()]


class CodexProtocolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.runtime = self.enterContext(patch.object(bridge, "_runtime", return_value=("synthetic-codex", Path("unused"), {"CODEX_HOME": "isolated"})))
        self.messages = [{"role": "user", "content": "synthetic-private-question"}]

    async def start(self, process):
        self.popen = self.enterContext(patch.object(bridge.subprocess, "Popen", return_value=process))
        chat = bridge.CodexChat()
        await chat.start(self.messages, Settings(codex_model="synthetic-model"))
        return chat

    async def test_isolated_ephemeral_prompt_transcript_stream_and_cleanup(self):
        process = FakeProcess(final_events())
        with patch.object(db, "connect", side_effect=AssertionError("must not read patient records")):
            chat = await self.start(process)
            directory = Path(chat.directory.name)
            self.assertEqual([item async for item in chat.events()], [("delta", {"text": "پاسخ ساختگی"}), ("done", {})])
        requests = process.sent()
        params = next(item["params"] for item in requests if item.get("method") == "thread/start")
        self.assertEqual(params["baseInstructions"], bridge.SYSTEM_PROMPT)
        self.assertEqual(params["developerInstructions"], "")
        self.assertEqual(params["model"], "synthetic-model")
        self.assertTrue(params["ephemeral"])
        for key in ("environments", "selectedCapabilityRoots", "runtimeWorkspaceRoots"):
            self.assertEqual(params[key], [])
        self.assertEqual(params["sandbox"], "read-only")
        self.assertEqual(params["approvalPolicy"], "never")
        turn = next(item["params"] for item in requests if item.get("method") == "turn/start")
        self.assertEqual(json.loads(turn["input"][0]["text"]), {"messages": self.messages})
        self.assertNotIn("thread/resume", [item.get("method") for item in requests])
        command = self.popen.call_args.args[0]
        for feature in bridge.DISABLED_FEATURES:
            self.assertIn("features." + feature + "=false", command)
        self.assertIn("--strict-config", command)
        self.assertEqual(self.popen.call_args.kwargs["stderr"], subprocess.DEVNULL)
        self.assertEqual(self.popen.call_args.kwargs["cwd"], str(directory))
        self.assertNotEqual(directory, Path.cwd())
        self.assertTrue(process.terminated)
        self.assertTrue(process.stdin.was_closed)
        self.assertTrue(process.stdout.closed)
        self.assertGreater(process.waits, 0)
        self.assertFalse(directory.exists())

    async def test_notifications_before_rpc_reply_are_not_lost(self):
        events = final_events()
        process = FakeProcess(events[2:], early=events[:2])
        chat = await self.start(process)
        self.assertEqual([item async for item in chat.events()][0], ("delta", {"text": "پاسخ ساختگی"}))

    async def test_commentary_and_reasoning_never_stream(self):
        process = FakeProcess([event("item/started", item={"id": "comment", "type": "agentMessage", "phase": "commentary"}),
                               event("item/agentMessage/delta", itemId="comment", delta="secret-commentary"),
                               event("item/started", item={"id": "reason", "type": "reasoning"}), *final_events()])
        chat = await self.start(process)
        output = [item async for item in chat.events()]
        self.assertNotIn("secret-commentary", str(output))
        self.assertEqual(output[-1], ("done", {}))

    async def test_normal_user_message_lifecycle_is_ignored(self):
        echoed = {"id": "input", "type": "userMessage", "content": [{"type": "text", "text": "private-user-echo"}]}
        process = FakeProcess([event("item/started", item=echoed), event("item/completed", item=echoed), *final_events()])
        chat = await self.start(process)
        output = [item async for item in chat.events()]
        self.assertEqual(output, [("delta", {"text": "پاسخ ساختگی"}), ("done", {})])
        self.assertNotIn("private-user-echo", str(output))

    async def test_unexpected_tool_failed_turn_bad_json_eof_and_output_bound(self):
        cases = [[event("item/started", item={"id": "tool", "type": "commandExecution"})],
                 [event("turn/completed", turn={"status": "failed"})],
                 [{"id": 88, "method": "item/commandExecution/requestApproval", "params": {}}],
                 [{"error": {"message": "private-provider-error"}}], [], final_events("x" * 20001)]
        for events in cases:
            with self.subTest(events=len(events)):
                process = FakeProcess(events)
                chat = await self.start(process)
                with self.assertNoLogs("app", level="DEBUG"):
                    output = [item async for item in chat.events()]
                self.assertEqual(output[-1][0], "error")
                self.assertNotIn("private-provider-error", str(output))
                self.assertTrue(process.terminated)

    async def test_runtime_must_honor_ephemeral_and_instruction_isolation(self):
        process = FakeProcess(thread={"id": "thread", "ephemeral": False})
        with self.assertRaises(ServiceError) as error:
            await self.start(process)
        self.assertEqual(error.exception.status_code, 503)
        self.assertFalse(any(item.get("method") == "turn/start" for item in process.sent()))
        self.assertTrue(process.terminated)

    async def test_malformed_stream_never_echoes_provider_data(self):
        for raw in (b'private-invalid-json\n', b'{"method":"item/started","params":null}\n', b'[]\n'):
            process = FakeProcess()
            chat = await self.start(process)
            process.stdout.close()
            process.stdout = io.BytesIO(raw)
            output = [item async for item in chat.events()]
            self.assertEqual(output[-1][0], "error")
            self.assertNotIn("private-invalid-json", str(output))
            self.assertTrue(process.terminated)

    async def test_timeout_and_cancel_interrupt_reap(self):
        process = FakeProcess()
        chat = await self.start(process)
        with patch.object(chat, "_read", side_effect=TimeoutError):
            output = [item async for item in chat.events()]
        self.assertEqual(output[-1][1]["error"]["code"], "assistant_timeout")
        process = FakeProcess()
        chat = await self.start(process)
        started = asyncio.Event()
        async def blocked():
            started.set()
            await asyncio.Event().wait()
        async def consume():
            return [item async for item in chat.events()]
        with patch.object(chat, "_read", side_effect=blocked):
            task = asyncio.create_task(consume())
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(process.terminated)
        self.assertIn("turn/interrupt", [item.get("method") for item in process.sent()])
        self.assertIsNone(chat.directory)

    async def test_pre_stream_timeout_and_broken_process_cleanup(self):
        process = FakeProcess()
        self.enterContext(patch.object(bridge.subprocess, "Popen", return_value=process))
        chat = bridge.CodexChat()
        with patch.object(chat, "_rpc", side_effect=TimeoutError):
            with self.assertRaises(ServiceError) as error: await chat.start(self.messages, Settings())
        self.assertEqual(error.exception.status_code, 504)
        self.assertTrue(process.terminated)
        self.assertIsNone(chat.directory)

    async def test_cleanup_kills_unresponsive_process(self):
        process = FakeProcess()
        chat = await self.start(process)
        process.wait = unittest.mock.Mock(side_effect=[subprocess.TimeoutExpired("synthetic", 1), 0])
        await chat.close()
        self.assertTrue(process.killed)
        await chat.close()


class AssistantValidationTests(unittest.TestCase):
    def test_order_roles_limits_and_no_extra_fields(self):
        valid = {"messages": [{"role": "user", "content": "  synthetic  "}]}
        self.assertEqual(AssistantRequest.model_validate(valid).messages[0].content, "synthetic")
        for body in ({}, {**valid, "system": "forged"}, {"messages": []},
                     {"messages": [{"role": "system", "content": "forged"}]},
                     {"messages": [{"role": "assistant", "content": "forged"}]},
                     {"messages": [{"role": "user", "content": " "}]},
                     {"messages": [{"role": "user", "content": "x" * 4001}]},
                     {"messages": [{"role": "user", "content": "x", "session_id": "forged"}]},
                     {"messages": valid["messages"] * 2}):
            with self.assertRaises(ValidationError): AssistantRequest.model_validate(body)
        pair = [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]
        AssistantRequest.model_validate({"messages": pair * 19 + valid["messages"]})
        with self.assertRaises(ValidationError): AssistantRequest.model_validate({"messages": pair * 20 + valid["messages"]})
        with self.assertRaises(ValidationError):
            AssistantRequest.model_validate({"messages": [{"role": "user", "content": "x" * 4000},
                {"role": "assistant", "content": "y" * 20000}] * 2 + valid["messages"]})

    def test_dedicated_home_config_validation_and_environment_allowlist(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"APP_LLM_API_KEY": "never-inherit", "APP_DB_PATH": "never-inherit"}), \
             patch.object(bridge.shutil, "which", return_value=__file__), patch.object(bridge, "_check_protocol"):
            home = Path(directory)
            executable, actual, environment = bridge._runtime(Settings(codex_home=directory))
            self.assertEqual(actual, home.resolve())
            self.assertEqual(environment["CODEX_HOME"], str(actual))
            self.assertNotIn("APP_LLM_API_KEY", environment)
            self.assertNotIn("APP_DB_PATH", environment)
            (home / "skills" / ".system").mkdir(parents=True)
            bridge._runtime(Settings(codex_home=directory))
            (home / "skills" / "custom").mkdir()
            with self.assertRaises(ServiceError): bridge._runtime(Settings(codex_home=directory))
            (home / "skills" / "custom").rmdir()
            (home / "config.toml").write_text('developer_instructions="ambient"', encoding="utf-8")
            with self.assertRaises(ServiceError): bridge._runtime(Settings(codex_home=directory))
            (home / "config.toml").unlink()
            (home / "AGENTS.md").write_text("ambient", encoding="utf-8")
            with self.assertRaises(ServiceError): bridge._runtime(Settings(codex_home=directory))
        for directory in (None, ".", str(Path.cwd()), str(Path.home() / ".codex")):
            with self.assertRaises(ServiceError): bridge._runtime(Settings(codex_home=directory))
        for key in ("APP_CODEX_HOME", "APP_CODEX_MODEL"):
            with patch.dict(os.environ, {key: "invalid\nvalue"}):
                with self.assertRaisesRegex(ValueError, key): Settings()

    def test_old_protocol_fails_closed(self):
        bridge._check_protocol.cache_clear()
        def generate(command, **kwargs):
            root = Path(command[-1]) / "v2"; root.mkdir()
            (root / "ThreadStartParams.json").write_text('{"properties":{"ephemeral":{}}}', encoding="utf-8")
        with patch.object(bridge.subprocess, "run", side_effect=generate):
            with self.assertRaises(ServiceError): bridge._check_protocol("synthetic", 1)

    def test_per_doctor_and_global_slots(self):
        bridge.ACTIVE.clear()
        self.addCleanup(bridge.ACTIVE.clear)
        bridge.reserve("doctor-a")
        with self.assertRaises(ServiceError): bridge.reserve("doctor-a")
        bridge.reserve("doctor-b")
        with self.assertRaises(ServiceError): bridge.reserve("doctor-c")
        bridge.release("doctor-a"); bridge.reserve("doctor-c")
        self.assertEqual(bridge.ACTIVE, {"doctor-b", "doctor-c"})


class AssistantAPITests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"APP_DB_PATH": str(Path(directory) / "assistant.db"), "APP_ADMIN_USERNAME": "",
            "APP_ADMIN_PASSWORD": "", "APP_DEMO_DOCTOR_PASSWORD": "", "APP_DOCTOR_AUTO_VERIFY": "true", "APP_CODEX_HOME": ""}))
        self.client = self.enterContext(TestClient(app))
        self.doctor = register_doctor(self.client)
        self.body = {"messages": [{"role": "user", "content": "synthetic-private-question"}]}
        bridge.ACTIVE.clear()
        self.addCleanup(bridge.ACTIVE.clear)

    def test_stream_contract_no_record_writes_and_release(self):
        async def events(self):
            yield "delta", {"text": "پاسخ ساختگی"}
            yield "done", {}
        with closing(db.connect()) as connection: before = list(connection.iterdump())
        with patch.object(bridge.CodexChat, "start", new_callable=AsyncMock) as start, \
             patch.object(bridge.CodexChat, "events", events), self.assertNoLogs("app", level="DEBUG"):
            response = self.client.post("/v1/doctor/assistant/messages", json=self.body)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn('event: delta\ndata: {"text": "پاسخ ساختگی"}', response.text)
        self.assertIn("event: done", response.text)
        self.assertEqual(start.call_args.args[0], self.body["messages"])
        self.assertFalse(bridge.ACTIVE)
        with closing(db.connect()) as connection: self.assertEqual(before, list(connection.iterdump()))

    def test_roles_and_unknown_login(self):
        with closing(db.connect()) as connection, connection:
            connection.execute("UPDATE doctors SET verified=0,review_status='pending' WHERE id=?", (self.doctor["id"],))
        self.assertEqual(self.client.post("/v1/doctor/assistant/messages", json=self.body).status_code, 403)
        register_patient(self.client)
        self.assertEqual(self.client.post("/v1/doctor/assistant/messages", json=self.body).status_code, 403)
        admin = TestClient(app); self.addCleanup(admin.close)
        with admin_account(admin): self.assertEqual(admin.post("/v1/doctor/assistant/messages", json=self.body).status_code, 403)
        self.client.post("/v1/auth/logout")
        self.assertEqual(self.client.post("/v1/doctor/assistant/messages", json=self.body).status_code, 401)

    def test_validation_unconfigured_and_busy_errors_safe(self):
        response = self.client.post("/v1/doctor/assistant/messages", json={"messages": [{"role": "system", "content": "private-marker"}]})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("private-marker", response.text)
        response = self.client.post("/v1/doctor/assistant/messages", json=self.body)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "assistant_unavailable")
        self.assertFalse(bridge.ACTIVE)
        bridge.reserve(self.doctor["id"])
        response = self.client.post("/v1/doctor/assistant/messages", json=self.body)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "5")

    def test_static_route_stream_controls_and_memory_only(self):
        response = self.client.get("/doctor")
        self.assertEqual(response.status_code, 200)
        for value in ('hash==="#/assistant"', 'id="assistant-stop"', 'id="assistant-new"', 'text/event-stream',
                      'setInterval(heartbeat,20000)', 'assistantHistory=[]', 'reader?.cancel()', 'response.status===403'):
            self.assertIn(value, response.text)
        for value in ("localStorage", "sessionStorage", "innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            self.assertNotIn(value, response.text)
