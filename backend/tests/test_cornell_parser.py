"""Tests for Cornell Class Roster API v2.0 client, parser, and VAPID keygen."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from py_vapid import Vapid

from app.config import generate_vapid_keypair
from app.providers.base import RateLimitedError, UpstreamUnavailableError
from app.providers.cornell import CornellRosterApiProvider, parse_cornell_classes_payload

SAMPLE_CORNELL_PAYLOAD = {
    "status": "success",
    "data": {
        "classes": [
            {
                "subject": "CS",
                "catalogNbr": "2110",
                "titleShort": "OO Prog & Data Structures",
                "titleLong": "Object-Oriented Programming and Data Structures",
                "description": "Intermediate programming.",
                "crseId": 351740,
                "enrollGroups": [
                    {
                        "componentsRequired": ["LEC", "DIS"],
                        "classSections": [
                            {
                                "ssrComponent": "LEC",
                                "section": "001",
                                "classNbr": 6582,
                                "openStatus": "O",
                                "campus": "MAIN",
                                "instrModeDescrshort": "In Person",
                                "meetings": [
                                    {
                                        "pattern": "TR",
                                        "timeStart": "10:10AM",
                                        "timeEnd": "11:25AM",
                                        "instructors": [
                                            {"firstName": "Erasmo", "middleName": "", "lastName": "Tani"}
                                        ],
                                    }
                                ],
                            },
                            {
                                "ssrComponent": "DIS",
                                "section": "202",
                                "classNbr": 6584,
                                "openStatus": "C",
                                "campus": "MAIN",
                                "instructionMode": "P",
                                "meetings": [],
                            },
                        ],
                    }
                ],
            }
        ]
    },
}


def test_parse_cornell_classes_payload() -> None:
    raw = json.dumps(SAMPLE_CORNELL_PAYLOAD).encode("utf-8")
    courses = parse_cornell_classes_payload(raw, roster="SP27")
    assert len(courses) == 1
    c = courses[0]
    assert c.roster == "SP27"
    assert c.subject == "CS"
    assert c.catalog_nbr == "2110"
    assert len(c.sections) == 2

    lec, dis = c.sections
    assert lec.class_nbr == 6582
    assert lec.open_status == "O"
    assert lec.components_required == ["LEC", "DIS"]
    assert lec.meetings_summary == "TR 10:10AM-11:25AM"
    assert lec.instructors_summary == "Erasmo Tani"

    assert dis.class_nbr == 6584
    assert dis.open_status == "C"
    assert dis.meetings_summary == "TBA"
    assert dis.instructors_summary == "Staff"


def test_generated_vapid_keys_accepted_by_pyvapid() -> None:
    pub, priv = generate_vapid_keypair()
    assert len(pub) > 40
    assert len(priv) > 30
    vapid = Vapid.from_string(private_key=priv)
    assert vapid.public_key is not None


@respx.mock
@pytest.mark.asyncio
async def test_cornell_provider_http_and_errors() -> None:
    base = "https://classes.cornell.edu/api/2.0"
    respx.get(f"{base}/config/rosters.json").mock(
        return_value=httpx.Response(
            200,
            json={"status": "success", "data": {"rosters": [{"slug": "SP27", "descr": "Spring 2027", "isDefaultRoster": "Y", "archiveMode": "N"}]}},
        )
    )
    respx.get(f"{base}/config/subjects.json").mock(
        return_value=httpx.Response(
            200,
            json={"status": "success", "data": {"subjects": [{"value": "CS", "descr": "Computer Science"}]}},
        )
    )
    respx.get(f"{base}/search/classes.json").mock(
        side_effect=[
            httpx.Response(200, json=SAMPLE_CORNELL_PAYLOAD),
            httpx.Response(429, headers={"Retry-After": "12"}),
            httpx.Response(503),
        ]
    )

    provider = CornellRosterApiProvider(base_url=base)
    try:
        rosters = await provider.fetch_rosters()
        assert len(rosters) == 1
        assert rosters[0].slug == "SP27"
        assert rosters[0].is_default is True

        subjects = await provider.fetch_subjects("SP27")
        assert subjects[0].value == "CS"

        res = await provider.fetch_subject_classes("SP27", "CS")
        assert len(res.courses) == 1

        with pytest.raises(RateLimitedError) as rl_exc:
            await provider.fetch_subject_classes("SP27", "CS")
        assert rl_exc.value.retry_after_sec == 12.0

        with pytest.raises(UpstreamUnavailableError):
            await provider.fetch_subject_classes("SP27", "CS")
    finally:
        await provider.close()
