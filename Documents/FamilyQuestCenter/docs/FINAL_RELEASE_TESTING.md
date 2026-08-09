# Family Quest Center Final Release Testing

## Automated baseline
Run:

`python -W error::ResourceWarning -m unittest discover tests -v`

All tests must pass before hosted deployment.

## Manual role checks
- Public landing, membership, registration, privacy, terms, and contact
- Parent sign-in, PIN lock/unlock, dashboard, approvals, reports, and family settings
- Child profile selection, Assigned Quests, Assigned Adventures, rewards, achievements, and completion actions
- Application Owner dashboard, account lookup, diagnostics, reports, settings, and backup/restore

## End-to-end clean database
1. Initialize the Application Owner.
2. Open `/register`.
3. Complete billing or the configured test checkout.
4. Create the family account.
5. Create the Parent PIN.
6. Complete Guided Setup.
7. Add a child, assign a Quest, and assign an Adventure.
8. Complete and approve the Quest and Adventure.
9. Request, approve, and redeem a Reward.
10. Archive and restore a Child, Quest, Adventure, and Reward.

## Platform checks
- Desktop browser
- Phone
- Tablet
- Railway deployment
- Database persistence after redeploy
- Email invitation and recovery links
- Cross-family isolation
