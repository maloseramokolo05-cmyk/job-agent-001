from job_sources.relevance import board_company_name, south_africa_relevant


def test_south_africa_location_filter():
    assert south_africa_relevant("Pretoria")
    assert south_africa_relevant("Remote", "This role is open to candidates in South Africa")
    assert not south_africa_relevant("Remote - United States", "Applicants must be based in the US")
    assert not south_africa_relevant("London", "Hybrid role")


def test_board_company_name():
    assert board_company_name("2u") == "2U"
    assert board_company_name("assist-world") == "Assist World"
