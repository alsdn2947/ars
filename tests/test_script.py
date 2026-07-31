from ars_voice.script import PauseProfile, build_script


def test_sentence_split_and_pauses():
    profile = PauseProfile()
    script = build_script("안녕하십니까. 반갑습니다.", profile=profile, auto_phrase=False)
    assert len(script.segments) == 2
    assert script.segments[0].text == "안녕하십니까."
    assert script.segments[0].pause_ms == profile.sentence_ms
    # 마지막 세그먼트는 여운(tail) 길이
    assert script.segments[1].pause_ms == profile.tail_ms


def test_comma_split_precise():
    profile = PauseProfile()
    script = build_script("첫째, 둘째, 셋째입니다.", profile=profile, auto_phrase=False, phrasing="precise")
    assert [s.text for s in script.segments] == ["첫째", "둘째", "셋째입니다."]
    assert script.segments[0].pause_ms == profile.comma_ms


def test_flow_mode_single_segment():
    """flow 모드: 전체 멘트가 한 세그먼트로 합쳐져 엔진이 흐름을 처리한다."""
    profile = PauseProfile()
    script = build_script(
        "안녕하십니까. 고객센터입니다. / 상담원 연결은 0번입니다. // 감사합니다.",
        phrasing="flow", profile=profile,
    )
    assert len(script.segments) == 1
    text = script.segments[0].text
    # 수동 표기는 문장 부호로 변환된다
    assert "/" not in text
    assert "안녕하십니까." in text and "감사합니다." in text
    assert "영번입니다" in text  # 발음 정규화도 적용
    assert script.segments[0].pause_ms == profile.tail_ms


def test_flow_mode_empty_text():
    script = build_script("   ", phrasing="flow")
    assert script.segments == []


def test_natural_mode_keeps_sentence_whole():
    """natural 모드: 쉼표는 분할하지 않고 문장 전체를 한 세그먼트로 유지."""
    script = build_script("첫째, 둘째, 셋째입니다. 감사합니다.", auto_phrase=True, phrasing="natural")
    assert [s.text for s in script.segments] == ["첫째, 둘째, 셋째입니다.", "감사합니다."]


def test_natural_mode_honors_manual_marks():
    profile = PauseProfile()
    script = build_script("안내를 시작합니다. // 잠시만요.", phrasing="natural", profile=profile)
    assert script.segments[0].pause_ms == profile.long_ms


def test_manual_pause_marks():
    profile = PauseProfile()
    script = build_script("잠시만 기다려 주세요. // 곧 연결됩니다.", profile=profile, auto_phrase=False)
    texts = [s.text for s in script.segments]
    assert texts == ["잠시만 기다려 주세요.", "곧 연결됩니다."]
    assert script.segments[0].pause_ms == profile.long_ms


def test_auto_phrase_inserts_pause_precise():
    script = build_script("상담을 원하시면 0번을 눌러 주세요.", auto_phrase=True, phrasing="precise")
    texts = [s.text for s in script.segments]
    assert texts[0].endswith("원하시면")
    assert len(texts) == 2


def test_normalization_applied():
    script = build_script("1588-1234로 전화 주세요.")
    joined = " ".join(s.text for s in script.segments)
    assert "일오팔팔" in joined


def test_punctuation_kept_for_intonation():
    script = build_script("감사합니다.", auto_phrase=False)
    assert script.segments[0].text == "감사합니다."
