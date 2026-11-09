# CardChart design guidance

## Direction and status

On 8 November 2026 the user requested PP Scheduling's design guidance, preferred
the supplied Collectr phone screenshots to the first CardChart mockup, and made
mobile a priority. This document adapts that guidance to CardChart. It governs
future UI work; it does not describe an implemented redesign. The user preferred
the second study's layout, then requested Performance and a more distinctive graph.
That preference confirms the general direction; the new additions await review.
The user explicitly clarified that the value-over-time chart must remain. Change
its visual treatment, not its purpose; mover bars are supporting detail.
The restored chart direction was preferred. Inspect values directly on hover,
with touch and keyboard access; omit the separate slider.

The user clarified that **binder views belong to the existing goals section**.
A binder is a presentation of a curated goal, not a separate collection, inventory
allocation or new named-group data model. Keep Cards and Binder views within the
same goal. Goal membership and accepted versions retain their existing owners.

[Product direction](docs/product-direction.md) owns product intent. Source and
tests establish current behaviour. [Component guides](docs/README.md) own data
and workflow contracts; this document owns visual direction and design delivery.

## Reference and provenance

- Process and shared UI principles: PP Scheduling's local `DESIGN.md` and
  `AGENTS.md`, read on 8 November 2026. Its cited reference is James's
  [design baseline at 3f4fe18](https://github.com/The-Smart-Elephant/production-scheduler/blob/3f4fe18879c5bd503ecaaea4bbb49d363b84d756/DESIGN.md).
  The inspected checkout was at that commit with uncommitted guidance updates.
  The inspected DESIGN file's SHA-256 was
  `10f066638ccb8a50695df3b450ca1a486de6f404736dd92b880e314c9468d971`.
- Visual reference: user-supplied `28200.png` (Collectr overview) and `28201.png`
  (collection gallery), attached to the 8 November conversation. Use their black
  canvas, restrained teal, strong value hierarchy, prominent card art and labelled
  mobile navigation. Their account values are not CardChart data.
- [Mobile and goal study](artifacts/design-review-v2/cardchart-mobile-binders.html)
  is the user's preferred layout direction. The
  [performance revision](artifacts/design-review-v3/cardchart-performance.html)
  extends that direction with illustrative baselines and is pending review. The
  [first study](artifacts/design-review/cardchart-concepts.html) remains historical
  evidence; it is not an accepted design baseline.

Transfer PP's reference-based process, readable typography, shared components,
progressive disclosure and preservation of backend facts. Do not copy PP branding,
magenta actions, scheduling roles, Gantt geometry, publication rules or demo data.
The user's collector screenshots take precedence over PP's pale desktop canvas.

## Visual foundation

| Element | CardChart direction |
| --- | --- |
| Typography | Locally hosted Source Sans 3, normal weight as the default. Establish hierarchy through size, spacing and contrast. Use tabular numerals for counts and money. The study includes the font and its SIL licence. |
| Scale | Start around 15–16px body, 14–16px controls and 24px page titles. Make the primary collection value larger. Supporting text stays readable; do not compress metadata to fit more cards. |
| Surfaces | Black collector canvas, restrained dark surfaces and subtle neutral borders. Let art and content carry the page. Avoid a blue-grey rounded panel around the entire application and boxes around every supporting fact. |
| Colour | Teal identifies selection and primary actions. Owned, missing, unavailable and stale states also use explicit text or symbols; colour alone is insufficient. Preserve readable contrast. |
| Chart identity | Keep an interactive value-over-time line chart. Use a warm unfilled line, restrained vertical ticks, a teal square cursor, visible date/value axes and snapshot inspection. Signed teal/coral movement bars support the timeline. Period change and since-added change have different baselines; label both. |
| Geometry | Consistent spacing and aligned edges. Controls use restrained corners, card art preserves its aspect ratio, and the grid leaves room for names and printing identity. |
| Controls | Reuse one owner for buttons, search, filters, navigation and inspectors. Use native form controls until a custom control has a demonstrated need and equivalent keyboard/validation behaviour. |
| Icons | One consistent local icon set or authored SVG style. Icon-only controls need accessible names. Keep labels on primary mobile navigation; no tooltip-only phone actions. |

These are presentation targets, not permission to add a frontend framework,
dependency, theme system or parallel business-logic layer. Production shared
choices belong in the existing base template, stylesheet and workflow components.

## Mobile and desktop composition

- Design the phone layout deliberately. Review 360px, 390px and 430px widths;
  use the supplied 900px-wide screenshots as visual references, not CSS dimensions.
- Keep the mobile main destinations concise: Home, Collection, Goals and Performance. Put
  import and reviewed reconciliation under clear secondary actions. They remain
  separate workflows, not a single blind sync action.
- Use labelled bottom navigation with at least 44px interaction targets. Reserve
  content space and device safe-area padding so controls never cover cards,
  pagination, messages or the final action. Avoid competing scroll containers.
- Collection uses a readable two-column card gallery where space allows. Preserve
  full artwork, exact printing/finish, quantity and price. Permit names to wrap.
  At narrow widths or enlarged text, reduce columns instead of clipping content.
- On desktop, use the available width for a rail or header, wider grids and a
  side inspector. Do not stretch a phone screen or shrink a desktop screenshot.
- Keep scope, filters, selected goal and reading position when opening/closing
  details or switching a goal's presentation. Explicit navigation may reset scroll.
  Responsive changes alone must not reset user state.

## Goals and binder views

The goal library shows curated cover art, name, owned/total, remaining count and a
clear action to continue. The goal page keeps progress, owned guide value, missing
guide cost, ownership filters and Cardmarket Wants List export available.

Cards view supports fast inspection and filtering. Binder view presents stable,
ordered pockets from that same manifest, with visible missing slots. Start the
study with a three-by-three page; adapt layout or offer Cards view when enlarged
text would make the pockets unreadable. Page controls must name their destination
and work without swiping or dragging. Do not reorder or close gaps merely to hide
missing or owned entries; if filtering highlights pockets, say so explicitly.

A pocket opens exact printing/version details. Do not silently create another
ownership record, allocate inventory to a binder, change membership, or duplicate
a card's value. One inventory row may satisfy several goals, so collection value
must not be calculated by summing goal values.

## Price and ownership information

The user wants **free sources**, GBP collection value and the estimated cost to
complete goals. Paid feeds, advertising and subscription upsells are out of scope.
Guide estimates are not UK sale proceeds, condition-specific offers or checkout
totals. Keep estimate labels, meaningful freshness warnings and priced coverage
visible. Put detailed source/FX dates and identifiers in the price inspector.

Unknown is not zero. Partial totals must say they are partial. Full-goal and
full-inventory totals retain their scope when a view is filtered or paginated.
Trend charts require suitable history; mock history is labelled illustrative and
does not imply implemented performance or profit tracking.

### Proposed performance view

The user requested increase/decrease since a card was added. The study interprets
this as guide-value change since the first valid guide price recorded when added,
not the purchase price or an inferred acquisition date. Production tracking must
start when a usable baseline exists; imported older holdings cannot claim history
that was never recorded. Current storage does not provide this guide-price history.

Compare exact printing/finish lots using their remaining quantities. New copies
need their own baseline; adding quantity must not appear as market appreciation.
Exclude disposed quantities from this current-holdings view. For comparable lots,
sum `(current guide - starting guide) * remaining quantity`; divide that change by
the sum of comparable starting values for the percentage. Do not average per-card
percentages. A zero starting value has no meaningful percentage.

Show comparable-holdings coverage and exclude missing prices/baselines from both
sides. Filters change the mover list, not headline scope. GBP change can include
exchange-rate movement; retain original prices, source, timestamps and applied FX
evidence in any future implementation. Historical guide storage, lot tracking and
migration choices remain implementation planning. Purchase profit and realised
sale returns are outside the proposed metric.

Only show accepted versions from the maintained manifests. Preserve quantities,
notes, acquisition dates, inventory links and multi-printing ownership. The current
quick-update route can clear other printings or ownership links; a visual redesign
must not conceal those effects behind an apparently harmless toggle. Existing
legacy prices and refresh behaviour remain until a separate decision changes them.

## Inspection and interaction

Move detailed editing out of every gallery card. A deliberate card inspection can
use a side drawer on desktop and a full-width sheet or detail screen on mobile.
If modal, contain focus, support Escape and an obvious Close control, then restore
focus and scroll to the originating card. Changes of version update the displayed
identity, guide value and marketplace destination together. Missing prices have a
clear unavailable state. Loading, empty search, failure and stale data need explicit
states; never invent successful data when a request fails.

Preserve keyboard operation, reduced-motion preferences and zoom/reflow. Tooltips
are supplementary: delay pointer hints, show keyboard labels promptly, and allow
Escape dismissal. Avoid gratuitous motion, glass effects and decorative charts.

## Reference-based delivery

1. Read this guidance, the owning component guide, relevant source and tests.
   Inspect the user's preferred screenshots and the current UI. State the intended
   hierarchy and the shared components to reuse.
2. Establish one representative phone screen before extending the pattern.
   Compare proportions, typography, spacing, density and emphasis against the
   reference. Preserve the brief rather than inventing another visual direction.
3. Render and personally inspect the actual result at representative phone and
   desktop widths, with equivalent content and theme. Separate sample-data
   differences from visual differences. Check long names and unavailable prices.
4. Correct the five largest visual deviations, or all if fewer. Batch fixes and
   confirm once. Explain intentional accessibility or functional departures.
   Use Impeccable for critique against this guidance, not to replace the reference.
5. Check affected interactions, keyboard/focus, scroll restoration, navigation
   clearance and overflow. Use the [verification runbook](docs/runbooks/verification.md)
   for production changes. Static studies validate their own interactions and do
   not establish runtime or database behaviour.
6. Show requested mockups inline and provide the artifact. Record actual check
   scope, limitations and unconfirmed acceptance. Keep implementation continuation
   in the [single work queue](docs/remaining-tasks.md), not a new competing plan.

No production implementation or database migration is authorised by adopting these
guidelines alone. Guidance transfer, mockup review and implementation acceptance
remain separate outcomes.
