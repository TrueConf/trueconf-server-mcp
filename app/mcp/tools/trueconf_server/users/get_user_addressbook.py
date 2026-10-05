from typing import Any

from fastmcp.server.dependencies import get_access_token

from app._client_api._trueconf_server.models import AddressBookFilters, AddressBookOutput
from app.mcp import _auth_required_dict, _request, mcp


async def _fetch_contacts_for_term(client_id: str, term: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Fetch all pages of contacts matching a single search term.

    Returns (contacts, error_dict). error_dict is None on success.
    Follows ``next_page_id`` until the server reports the end (-1).
    """
    contacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    page: int | None = None
    while page != -1:
        params = AddressBookFilters(search=term).model_dump(by_alias=True, exclude_none=True)
        if page is not None:
            params["page_id"] = page
        resp = await _request(
            "GET",
            f"users/{client_id}/addressbook",
            params=params,
            version="v4.1",
        )
        if "error" in resp:
            return [], resp
        for c in resp.get("contacts", []):
            cid = c.get("id")
            if cid is not None and cid not in seen:
                seen.add(cid)
                contacts.append(c)
        page = resp.get("next_page_id")
    return contacts, None


@mcp.tool(tags={"users", "addressbook", "read"})
async def get_user_addressbook(
    search: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> dict[str, Any]:
    """Get the authenticated user's address book (contacts).

    Returns the contacts of the authenticated user. Use it to view the full
    address book or to search for a contact by name and obtain their TrueConf
    ID, so participants can be added to a conference without knowing the exact
    ID beforehand.

    Requires TrueConf Server 5.5.6 or newer (API v4.1). On older servers the
    address book endpoint is not available and the tool returns
    ``endpoint_not_supported`` — tell the user to ask their administrator to
    upgrade the server.

    Note on multi-word search: the TrueConf Server ``filter_search`` accepts
    ONE word only — a query with a space (e.g. "Alice Lesova") returns an
    empty list, and there is no server-side exact-name match. This tool
    compensates: the input is stripped and split on whitespace, one request
    per word is sent, and results are intersected by contact id (a contact is
    returned only if it matches every word). Pass the full display name and
    let the tool resolve it.

    Note on identifiers: each contact has a short ``id`` (e.g. "elisa") and a
    ``uid`` (e.g. "elisa@video.example.net"). Use the ``id`` field when
    passing participants to create_conference/add_invitation. The server also
    accepts the full ``uid`` as a participant identifier, but ``id`` is the
    canonical short form.

    Args:
        search: Filter contacts by name (display name). When multiple words
            are given, each word is queried separately and results are
            intersected by id.
        page: Page number (single-word / full-book requests only)
        page_size: Number of records per page (single-word / full-book only)
    """
    token = get_access_token()
    if token is None:
        return _auth_required_dict()

    path_base = f"users/{token.client_id}/addressbook"

    if not search or not search.strip():
        filters = AddressBookFilters(page=page, page_size=page_size)
        raw = await _request(
            "GET",
            path_base,
            params=filters.model_dump(by_alias=True, exclude_none=True),
            version="v4.1",
        )
        if "error" in raw:
            return raw
        return AddressBookOutput.model_validate(raw).model_dump(exclude_none=True)

    terms = search.strip().split()
    if len(terms) == 1:
        filters = AddressBookFilters(search=terms[0], page=page, page_size=page_size)
        raw = await _request(
            "GET",
            path_base,
            params=filters.model_dump(by_alias=True, exclude_none=True),
            version="v4.1",
        )
        if "error" in raw:
            return raw
        return AddressBookOutput.model_validate(raw).model_dump(exclude_none=True)

    # Multi-word: one request per term, intersect by contact id.
    term_results: list[list[dict[str, Any]]] = []
    for term in terms:
        contacts, err = await _fetch_contacts_for_term(token.client_id, term)
        if err is not None:
            return err
        term_results.append(contacts)

    if not term_results:
        return AddressBookOutput(contacts=[], next_page_id=-1).model_dump(exclude_none=True)

    # Intersect by id, preserving the order of the first word's results.
    intersect_ids = {c["id"] for c in term_results[0]}
    for r in term_results[1:]:
        intersect_ids &= {c["id"] for c in r}
    first_by_id = {c["id"]: c for c in term_results[0]}
    intersected = [first_by_id[cid] for cid in intersect_ids if cid in first_by_id]
    return AddressBookOutput.model_validate({"contacts": intersected, "next_page_id": -1}).model_dump(exclude_none=True)
