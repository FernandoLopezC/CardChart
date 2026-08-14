# Product direction

CardChart is moving from price tracking toward collection and collection-goal tracking. A goal is a manually curated subset; it need not represent an entire Scryfall set. The initial goals are Middle-earth Classic Artist Cards associated with `hoc` and Japanese Mystical Archive cards associated with `soa`.

Each desired card appears once in a goal checklist and is missing or owned. Exact owned printings attach to that entry and retain the canonical Scryfall printing ID, set, collector number, finish, and language. Goal membership and accepted printings are explicit, not inferred for every card in a set or every printing of an Oracle card. Scryfall bulk and live data enrich printing metadata but do not define membership.

Existing pricing is legacy behavior. It remains available on inventory pages until removal is separately approved. Database migration work is out of scope.
