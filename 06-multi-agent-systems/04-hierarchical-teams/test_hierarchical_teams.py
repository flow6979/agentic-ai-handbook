from hierarchical_teams import LaunchManager, offline_llm


def test_two_levels_roll_up():
    fake = offline_llm()
    res = LaunchManager(llm_factory=lambda r: fake, verbose=False).run("launch app")
    assert [r.team for r in res.reports] == ["marketing", "engineering"]
    assert set(res.reports[0].worker_outputs) == {"copywriter", "social_media"}
    assert set(res.reports[1].worker_outputs) == {"backend_dev", "qa_engineer"}
    assert res.final.startswith("Launch plan")


def test_manager_sees_only_team_summaries_not_raw_worker_output():
    fake = offline_llm()
    LaunchManager(llm_factory=lambda r: fake, verbose=False).run("launch app")
    final_call = [m for m in fake.calls if "ROLE: Launch Manager" in m[0].content and "TEAM REPORTS" in m[-1].content][0]
    assert "output of ROLE: Copywriter" not in final_call[-1].content
    assert "Marketing: copy" in final_call[-1].content


def test_hallucinated_team_and_worker_are_skipped():
    fake = offline_llm(invent_bad_names=True)
    res = LaunchManager(llm_factory=lambda r: fake, verbose=False).run("launch app")
    assert "legal" in res.skipped and "marketing/designer" in res.skipped
    assert len(res.reports) == 2


def test_role_keys_for_per_level_models():
    seen, fake = [], offline_llm()
    LaunchManager(llm_factory=lambda r: seen.append(r) or fake, verbose=False).run("x")
    assert seen[0] == "manager" and "marketing_lead" in seen and "copywriter" in seen
