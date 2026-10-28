# Triage interface design

The existing forest identity is the shared system for login, patient, doctor
and administrator workspaces. This is a visual refinement, not a new product
or a claim of clinical validation or production readiness.

## Structure

- Modern-minimal workbench: top bar, role-specific navigation, scrollable work
  area and an anchored composer for conversations.
- Login: a quiet product introduction beside one focused account form; one
  column on small screens. No invented metrics, endorsements or decorative art.
- Reuse the existing routes and state ownership. No page-level theme changes.

## Tokens and typography

`src/app/static/shell.css` owns the shared tokens, including its portable
`:root` token export. Keep the forest accent, warm off-white canvas, white
surfaces, muted green-grey text, hairline rules and restrained danger states.
Use named spacing, radius, typography, focus and interaction tokens.

System fonts: Tahoma, Segoe UI and sans-serif; no external font requests.
Headings are upright, moderately weighted and sized by hierarchy. Persian RTL
is the default; free text uses automatic direction and technical values LTR.

## Components and states

- Buttons: 44px minimum target, one primary action, clear secondary/danger
  treatment, hover/focus/active/disabled/busy states and no unnecessary animation.
- Forms: visible labels, help text, consistent controls, explicit validation
  feedback and stable focus. Show progress without replacing a user's draft.
- Cards: quiet borders, useful headings and consistent spacing. Status chips
  convey real lifecycle state; never fabricated counts or clinical certainty.
- Conversation bubbles: readable line length and distinct sender styling;
  summaries/review stay in the existing conversation flow.
- Icons: small, decorative CSS masks from one consistent outline vocabulary;
  retain visible text and accessible labels for actions.

## Accessibility and responsive behavior

Use skip links, semantic sections/labels, visible keyboard focus, existing
drawer focus trapping/Escape behavior and reduced-motion support. Verify 320,
375, 414 and 768px plus desktop, including long text and expanded forms. Root
horizontal overflow uses clip; individual work areas scroll vertically.

## Copy and data truth

Brand the product as Triage. Remove demo/test-version wording from current UI,
while explicitly labeling fictional seed doctors and examples. A compact data
notice remains visible. AI output requires physician review; no secure,
compliant, clinically validated or production-ready claims are introduced.

Historical specifications/test fixtures and compatibility identifiers may retain
their original names. Keep the old returning-profile prefix solely to recognize
existing conversations; do not rewrite stored messages to match new branding.
