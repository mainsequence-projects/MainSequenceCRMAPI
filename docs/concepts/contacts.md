# Contacts

A contact represents a person being tracked, not a platform user. The contact
may have many current or historical [company affiliations](companies.md) and an owner selected
from the existing platform directory. Neither link grants authentication or
creates a user.

Creation requires at least one nonblank first name, last name, or email.
Email and phone methods are bounded arrays; duplicate normalized emails,
phone numbers, and tag UUIDs are rejected. A contact can carry a status key,
first/last-seen timestamps, a newsletter flag, an avatar reference, tags, and
social profiles. `socials` is one typed object with fixed, optional platform
keys: LinkedIn, X, Facebook, Instagram, Threads, Bluesky, Mastodon, TikTok,
YouTube, Snapchat, Pinterest, Reddit, GitHub, GitLab, Telegram, Discord,
WhatsApp, WeChat, and LINE. Values are HTTP(S) profile URLs; absent keys mean
no recorded profile. LinkedIn is a key within `socials`, not a separate
contact field. The company contract still has its own `linkedin_url`.
Server projections add `display_name`, `company_name`, and an open-task count.
`company_uid` and `company_name` are compatibility projections of one primary
current affiliation, not the full work history. Other concurrent current
affiliations are allowed. At most one current affiliation is primary.

Each affiliation is one company stint with `current`, `former`, or `unknown`
status and optional `started_period` and `ended_period`. A period retains its
source precision (`YYYY`, `YYYY-MM`, or `YYYY-MM-DD`); null means the source
did not supply it, not that it happened today. `first_seen` and `last_seen`
describe CRM contact activity, not employment dates. A change of primary
company preserves the old stint and creates a new one; the transition can
leave the prior company concurrent or mark it former with a known end period.

Editing uses an expected record version and a nonempty set of changes. Clearing
the last usable identity fails validation. When `tag_uids` is supplied in a
patch it is a complete replacement; omission leaves the current links alone.
Within `changes.socials`, only supplied platform keys change: `null` removes
one link, omission preserves it, and `changes.socials: null` clears all links.
Archiving a contact does not silently archive its tasks or work history.

Merging is a separate workflow: preview a survivor/loser pair and field
resolutions, review the proposed contact and related counts (including
affiliations), then execute with
both expected versions and the preview's plan hash. An ordinary contact patch
cannot retire another contact. Social profiles merge per platform: the
survivor's link wins a conflict by default, missing platforms are filled from
the loser, and an explicit `socials.<platform>` resolution can choose either
side for one platform.

See the [contact API](../api/contacts-companies.md) for paths and request bodies.
