from app.models.enums import Seniority
from app.models.user import User
from app.services.scoring import score_job_offer


def _make_profile(**overrides) -> User:
    defaults = dict(skills=[], location=None, seniority=None)
    defaults.update(overrides)
    return User(**defaults)


def test_score_is_zero_ish_when_nothing_matches():
    profile = _make_profile(skills=["Angular"], location="Barcelona", seniority=Seniority.senior)
    offer = {"title": "Cocinero", "description": "Restaurante busca cocinero", "location": "Sevilla"}
    score, reasoning = score_job_offer(profile, offer)
    assert score < 20
    assert "0/1 skills" in reasoning


def test_score_is_high_when_everything_matches():
    profile = _make_profile(skills=["Angular", "Python", "FastAPI"], location="Barcelona", seniority=Seniority.junior)
    offer = {
        "title": "Junior Full Stack Developer",
        "description": "Buscamos junior con Angular, Python y FastAPI",
        "location": "Barcelona, España",
    }
    score, reasoning = score_job_offer(profile, offer)
    assert score >= 90
    assert "3/3 skills" in reasoning
    assert "ubicación compatible" in reasoning
    assert "seniority" in reasoning


def test_more_matched_skills_scores_higher():
    profile = _make_profile(skills=["Angular", "Python", "FastAPI", "Docker"])
    offer_partial = {"title": "Dev", "description": "Usamos Angular", "location": ""}
    offer_full = {"title": "Dev", "description": "Usamos Angular, Python, FastAPI y Docker", "location": ""}

    score_partial, _ = score_job_offer(profile, offer_partial)
    score_full, _ = score_job_offer(profile, offer_full)
    assert score_full > score_partial


def test_score_without_profile_data_does_not_crash():
    profile = _make_profile()
    offer = {"title": "Cualquier puesto", "description": "", "location": None}
    score, reasoning = score_job_offer(profile, offer)
    assert score == 0
    assert isinstance(reasoning, str)
