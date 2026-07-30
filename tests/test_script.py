from ars_voice.script import PauseProfile, build_script


def test_sentence_split_and_pauses():
    profile = PauseProfile()
    script = build_script("안녕하십니까. 반갑습니다.", profile=profile, auto_phrase=False)
    assert len(script.segments) == 2
    assert script.segments[0].text == "안녕하십니까."
    assert script.segments[0].pause_ms == profile.sentence_ms
    # 마지막 세그먼트는 여운(tail) 길이
    assert script.segments[1].pause_ms == profile.tail_ms


def test_comma_split():
    profile = PauseProfile()
    script = build_script("첫째, 둘째, 셋째입니다.", profile=profile, auto_phrase=False)
    assert [s.text for s in script.segments] == ["첫째", "둘째", "셋째입니다."]
    assert script.segments[0].pause_ms == profile.comma_ms


def test_manual_pause_marks():
    profile = PauseProfile()
    script = build_script("잠시만 기다려 주세요. // 곧 연결됩니다.", profile=profile, auto_phrase=False)
    texts = [s.text for s in script.segments]
    assert texts == ["잠시만 기다려 주세요.", "곧 연결됩니다."]
    assert script.segments[0].pause_ms == profile.long_ms


def test_auto_phrase_inserts_pause():
    script = build_script("상담을 원하시면 0번을 눌러 주세요.", auto_phrase=True)
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
