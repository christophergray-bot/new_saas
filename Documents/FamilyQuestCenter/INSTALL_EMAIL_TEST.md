# Family Quest Center — Hosted Email Test Patch

Copy these files into the matching locations in the current Git project.
Do not copy a database file and do not store the Google App Password in source code.

## Railway variables

Add these to the `family-quest-center` service and click **Apply**:

- `MAIL_SERVER=smtp.gmail.com`
- `MAIL_PORT=587`
- `MAIL_USE_TLS=true`
- `MAIL_USERNAME=christopher.gray@familyquestcenter.com`
- `MAIL_PASSWORD=<Google 16-character App Password>`
- `MAIL_FROM=Family Quest Center <christopher.gray@familyquestcenter.com>`
- `MAIL_TIMEOUT=20`
- `APP_URL=<Railway public HTTPS URL>`

## Local verification

```bat
python -W error::ResourceWarning -m unittest discover tests -v
```

Expected test count increases by two.

## Commit and deploy

```bat
git status
git add .
git commit -m "Add hosted Google Workspace email test"
git push origin main
```

After Railway reports **Deployment successful**:

1. Sign in as the installation owner.
2. Open **Developer Center**.
3. Open **Email Test**.
4. Confirm the settings show **Configured**.
5. Select **Send Test Email**.
6. Check the installation-owner inbox and Spam folder.

The page sends only to the signed-in installation owner's account and never displays the SMTP password.
