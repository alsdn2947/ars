from ars_voice.normalizer import normalize, read_digits, read_sino


def test_read_sino_basic():
    assert read_sino(0) == "영"
    assert read_sino(3) == "삼"
    assert read_sino(12) == "십이"
    assert read_sino(115) == "백십오"
    assert read_sino(1000) == "천"
    assert read_sino(15000) == "만 오천"
    assert read_sino(100000000) == "일억"
    assert read_sino(20260730) == "이천이십육만 칠백삼십"


def test_phone_number_digit_reading():
    out = normalize("상담 전화는 1588-1234 입니다.")
    assert "일오팔팔, 일이삼사" in out
    out = normalize("02-1234-5678")
    assert out == "공이, 일이삼사, 오육칠팔"
    out = normalize("010-9876-5432로 연락주세요.")
    assert "공일공, 구팔칠육, 오사삼이" in out


def test_time_reading_native_hours():
    assert "아홉 시" in normalize("평일 09:00부터")
    assert "오후 여섯 시" in normalize("18시까지")
    assert "아홉 시 삼십 분" in normalize("9:30")
    # 오전/오후가 이미 있으면 중복하지 않는다
    out = normalize("오후 3시")
    assert out.count("오후") == 1
    assert "세 시" in out


def test_date_reading_irregular_months():
    assert "유월" in normalize("6월 1일")
    assert "시월" in normalize("10월 9일")
    assert "십이월" in normalize("12월 25일")


def test_money_reading():
    assert "만 오천원" in normalize("이용료는 15,000원입니다.")
    assert "삼만원" in normalize("30,000원")


def test_percent_and_decimal():
    assert "오십 퍼센트" in normalize("50% 할인")
    assert "삼 점 오" in normalize("금리 3.5")


def test_acronym_spelling():
    assert "에이알에스" in normalize("ARS 안내")
    assert "브이아이피" in normalize("VIP 고객")


def test_digit_reading_helper():
    assert read_digits("1588") == "일오팔팔"
    assert read_digits("010") == "공일공"
