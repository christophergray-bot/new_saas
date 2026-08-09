# HD-4 Account Recovery and Parent Two Email Invitations

This patch adds:

- Forgot-password email requests with a non-enumerating response.
- SHA-256-hashed, one-time reset tokens that expire after 60 minutes.
- Password reset pages and branded HTML email.
- Account session invalidation through `auth_version` after password changes.
- Parent Two invitation emails with hashed, one-time tokens that expire after 7 days.
- Invitation acceptance for either a new parent account or an existing account.
- Regression tests for password recovery and Parent Two invitation acceptance.

## Install

Copy the patch files into the matching locations in the main Git project. Do not copy a database file.

Run:

```bat
python -W error::ResourceWarning -m unittest discover tests -v
```

Then commit and deploy:

```bat
git status
git add .
git commit -m "Add password recovery and Parent Two email invitations"
git push origin main
```

No new Railway variables are required beyond the working email variables and `APP_URL`.

## Hosted manual test

1. Sign out and choose **Forgot password?**
2. Request a reset for Parent One.
3. Use the email link and set a new password.
4. Confirm the old password fails and the new password works.
5. Invite Parent Two from Parent Management.
6. Open the email as Parent Two, accept, and create the second parent account.
7. Confirm Parent Two can sign in and access the correct family only.
