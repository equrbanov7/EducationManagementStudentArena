"""
View tests for accounts app.

This module has been split into focused concern-based modules for better
maintainability.  All tests can be found in:

* test_auth_membership.py   — LoginViewTest, LoginRateLimitTest,
                               LogoutViewTest, PasswordResetViewTest
* test_auth_signup.py       — RegisterViewTest
* test_auth_otp.py          — OTPRateLimitViewTest
* test_profile_permissions.py — ProfileAccessTest, DashboardViewTest,
                                 RoleBasedAccessTest, PublicProfileViewTest
"""
