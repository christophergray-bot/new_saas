# FC-0019 — Family Settings Tenant Isolation

Parent-managed settings are stored in `family_settings` using the composite key
`(family_id, key)`. Installation-wide values such as registration mode and the
installation owner remain in the original `settings` table.

On first use after upgrade, existing shared values are copied to each existing
family as that family's starting values. Later changes are isolated.

Affected preferences include quest starting values, daily rules, quest XP
awards, Parent Area session duration, family locale values, and notification
preferences.
