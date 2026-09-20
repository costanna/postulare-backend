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


def test_java_does_not_match_javascript_and_sql_does_not_match_postgresql():
    # Regresión: con `skill in texto`, "java" casaba con cualquier oferta de
    # JavaScript. Un CV con Java Y JavaScript lo sufre de lleno.
    profile = _make_profile(skills=["Java", "SQL"])
    offer = {"title": "Frontend", "description": "JavaScript, TypeScript y PostgreSQL", "location": ""}

    score, reasoning = score_job_offer(profile, offer)

    assert score == 0
    assert "0/2 skills" in reasoning


def test_skills_with_symbols_match_as_whole_words():
    profile = _make_profile(skills=["C++", "C#", "Node.js"])
    offer = {"title": "Dev", "description": "Buscamos C++, C# y Node.js (no Java).", "location": ""}

    _, reasoning = score_job_offer(profile, offer)

    assert "3/3 skills" in reasoning


def test_long_cv_skill_list_is_not_penalised_for_the_skills_it_does_not_use():
    # Un CV real lista 25-30 skills; una oferta que menciona 5 de ellas es un
    # buen encaje y no debe puntuar como si casara 5 de 30 (~12/70).
    many = [f"skill{i}" for i in range(25)] + ["Python", "Angular", "Docker", "PostgreSQL", "Java"]
    profile = _make_profile(skills=many)
    offer = {"title": "Dev", "description": "Python, Angular, Docker, PostgreSQL y Java", "location": ""}

    score, reasoning = score_job_offer(profile, offer)

    assert score >= 70  # bloque de skills completo
    assert "5 de tus skills coinciden" in reasoning
    assert "/30" not in reasoning


def test_few_skills_keep_the_ratio_format():
    profile = _make_profile(skills=["Angular", "Python", "FastAPI"])
    offer = {"title": "Dev", "description": "Angular", "location": ""}

    _, reasoning = score_job_offer(profile, offer)

    assert "1/3 skills" in reasoning
