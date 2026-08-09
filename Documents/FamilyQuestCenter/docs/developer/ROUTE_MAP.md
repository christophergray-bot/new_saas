# Route Map

Generated from route decorators in `routes/`.

| Module | Handler | URL rule | Methods |
|---|---|---|---|
| `account` | `register` | `/register` | GET, POST |
| `account` | `login` | `/login` | GET, POST |
| `account` | `logout` | `/logout` | POST |
| `account` | `profile` | `/profile` | GET, POST |
| `account` | `change_password` | `/change-password` | GET, POST |
| `account` | `forgot_password` | `/forgot-password` | GET |
| `achievements` | `manager` | `/` | GET |
| `achievements` | `new` | `/new` | GET, POST |
| `achievements` | `edit` | `/<int:achievement_id>/edit` | GET, POST |
| `achievements` | `toggle` | `/<int:achievement_id>/toggle` | POST |
| `adventures` | `chains` | `/adventures` | GET |
| `adventures` | `new_chain` | `/adventures/new` | GET, POST |
| `adventures` | `edit_chain` | `/adventures/<int:adventure_id>/edit` | GET, POST |
| `adventures` | `assign` | `/adventures/<int:adventure_id>/assign` | GET, POST |
| `adventures` | `challenges` | `/challenges` | GET, POST |
| `adventures` | `child_chains` | `/<int:user_id>/adventures` | GET |
| `adventures` | `child_challenges` | `/<int:user_id>/family-challenges` | GET |
| `approvals` | `queue` | `/` | GET |
| `archive` | `center` | `/` | GET |
| `archive` | `category` | `/<kind>` | GET |
| `auth` | `setup_pin` | `/setup-pin` | GET, POST |
| `auth` | `login` | `/login` | GET, POST |
| `auth` | `logout` | `/logout` | POST |
| `child` | `dashboard` | `/<int:user_id>` | GET |
| `child` | `character` | `/<int:user_id>/character` | GET, POST |
| `child` | `trophy_room` | `/<int:user_id>/achievements` | GET |
| `child` | `complete` | `/complete/<int:assignment_id>` | GET |
| `child` | `complete_today_journey` | `/<int:user_id>/journeys/<int:journey_instance_id>/complete` | GET |
| `child` | `progress` | `/<int:user_id>/progress` | GET |
| `child` | `timeline` | `/<int:user_id>/timeline` | GET |
| `children` | `list_children` | `/` | GET |
| `children` | `add_child` | `/add` | GET, POST |
| `children` | `view_child` | `/<int:child_id>` | GET |
| `children` | `edit_child` | `/<int:child_id>/edit` | GET, POST |
| `children` | `toggle_child` | `/<int:child_id>/toggle` | POST |
| `content_packs` | `manager` | `/` | GET |
| `content_packs` | `detail` | `/<pack_key>` | GET |
| `content_packs` | `install` | `/<pack_key>/install` | POST |
| `content_packs` | `archive` | `/<pack_key>/archive` | POST |
| `content_packs` | `restore` | `/<pack_key>/restore` | POST |
| `developer` | `dashboard` | `/` | GET |
| `developer` | `health` | `/health` | GET |
| `developer` | `migrations` | `/migrations` | GET |
| `developer` | `audit_log` | `/audit-log` | GET |
| `developer` | `errors` | `/errors` | GET |
| `developer` | `clear_errors` | `/errors/clear` | POST |
| `developer` | `content_validator` | `/content` | GET |
| `developer` | `configuration` | `/configuration` | GET |
| `developer` | `diagnostics` | `/diagnostics` | GET |
| `home` | `index` | `/` | GET |
| `home` | `family_dashboard` | `/family` | GET |
| `journeys` | `library` | `/` | GET |
| `journeys` | `new` | `/new` | GET |
| `journeys` | `edit` | `/<int:journey_id>/edit` | GET |
| `maintenance` | `center` | `/` | GET |
| `maintenance` | `backup` | `/backup` | POST |
| `maintenance` | `download_backup` | `/backup/<name>/download` | GET |
| `maintenance` | `remove_backup` | `/backup/<name>/delete` | POST |
| `maintenance` | `restore` | `/backup/<name>/restore` | POST |
| `maintenance` | `export_data` | `/export` | GET |
| `maintenance` | `integrity` | `/integrity` | GET |
| `missions` | `today` | `/` | GET |
| `missions` | `generate_today` | `/generate` | POST |
| `missions` | `schedules` | `/schedules` | GET |
| `missions` | `add_schedule` | `/schedules/add` | GET, POST |
| `missions` | `edit_schedule` | `/schedules/<int:schedule_id>/edit` | GET, POST |
| `missions` | `toggle_schedule` | `/schedules/<int:schedule_id>/toggle` | POST |
| `notifications` | `center` | `/` | GET |
| `onboarding` | `family_setup` | `/` | GET |
| `onboarding` | `finish_family_setup` | `/finish` | POST |
| `onboarding` | `explorer_training` | `/explorer/<int:user_id>` | GET |
| `onboarding` | `explorer_training_complete` | `/explorer/<int:user_id>/complete` | POST |
| `parent` | `dashboard` | `/` | GET |
| `parent` | `settings` | `/settings` | GET, POST |
| `parent_management` | `overview` | `/` | GET |
| `parent_management` | `invite_parent_two` | `/invite` | POST |
| `parent_management` | `cancel_invitation` | `/invitation/cancel` | POST |
| `parent_management` | `remove_parent_two` | `/remove/<int:account_id>` | POST |
| `parent_management` | `security` | `/security` | GET |
| `parent_management` | `notifications` | `/notifications` | GET, POST |
| `parent_management` | `activity` | `/activity` | GET |
| `parent_management` | `family_settings` | `/family-settings` | GET, POST |
| `quests` | `library` | `/` | GET |
| `quests` | `new` | `/new` | GET, POST |
| `quests` | `edit` | `/<int:chore_id>/edit` | GET, POST |
| `quests` | `toggle` | `/<int:chore_id>/toggle` | GET |
| `quests` | `duplicate` | `/<int:chore_id>/duplicate` | GET |
| `reports` | `overview` | `/` | GET |
| `reward_shop` | `shop` | `/<int:user_id>/rewards` | GET |
| `reward_shop` | `detail` | `/<int:user_id>/rewards/<int:reward_id>` | GET |
| `reward_shop` | `request_reward` | `/<int:user_id>/rewards/<int:reward_id>/request` | POST |
| `reward_shop` | `history` | `/<int:user_id>/reward-history` | GET |
| `rewards` | `manager` | `/` | GET |
| `rewards` | `edit` | `/new` | GET, POST |
| `rewards` | `edit` | `/<int:reward_id>/edit` | GET, POST |
| `rewards` | `toggle_reward` | `/<int:reward_id>/toggle` | POST |
| `rewards` | `add_category` | `/categories` | POST |
| `rewards` | `toggle_category` | `/categories/<int:category_id>/toggle` | POST |
| `rewards` | `requests_queue` | `/requests` | GET |
| `rewards` | `approve` | `/requests/<int:request_id>/approve` | POST |
| `rewards` | `deny` | `/requests/<int:request_id>/deny` | POST |
| `rewards` | `redeem` | `/requests/<int:request_id>/redeem` | POST |
