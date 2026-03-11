"""
Signup lookups for accounts.
"""

from apps.organizations.models import Country, Organization
from core.constants import OrganizationType


def get_signup_lookup_payload():
    """Return country and organization lookup data used during signup."""
    countries = list(Country.objects.filter(is_active=True).values("code", "name").order_by("name"))
    country_codes = {country["code"] for country in countries}
    country_name_to_code = {country["name"].strip().lower(): country["code"] for country in countries}
    organizations = []
    org_rows = (
        Organization.objects.filter(
            is_active=True,
            status="active",
            org_type__in={
                OrganizationType.SCHOOL,
                OrganizationType.UNIVERSITY,
                OrganizationType.COURSE_CENTER,
            },
        )
        .values("id", "name", "slug", "org_type", "country")
        .order_by("name")
    )

    for organization in org_rows:
        raw_country = (organization.get("country") or "").strip()
        normalized_country = raw_country.upper()
        country_code = ""
        if normalized_country in country_codes:
            country_code = normalized_country
        elif raw_country:
            country_code = country_name_to_code.get(raw_country.lower(), "")

        organizations.append(
            {
                "id": str(organization["id"]),
                "name": organization["name"],
                "slug": organization["slug"],
                "org_type": organization["org_type"],
                "country": raw_country,
                "country_code": country_code,
            }
        )

    return {
        "countries": countries,
        "organizations": organizations,
    }


__all__ = ["get_signup_lookup_payload"]
