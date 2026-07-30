"""한국어 ARS 발음 정규화.

TTS 엔진에 텍스트를 넘기기 전에, 숫자·기호·영문을 성우가 실제로 읽는
발음 그대로의 한글로 바꾼다. 엔진 자체 숫자 읽기에 맡기면 전화번호를
금액처럼 읽거나 시각을 한자어로 읽는 오독이 생기기 때문에 전 단계에서
확정한다.

적용 순서가 중요하다: 전화번호 → 시각 → 날짜 → 금액 → 퍼센트 →
일반 숫자 → 영문 약어. (앞 단계가 소비한 숫자는 뒷 단계에 노출되지 않는다.)
"""

from __future__ import annotations

import re

_SINO = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
_DIGIT_NAMES = ["공", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
_BIG_UNITS = ["", "만", "억", "조", "경"]

# 시각 읽기에 쓰는 고유어 수사 (1~12시)
_NATIVE_HOURS = {
    1: "한", 2: "두", 3: "세", 4: "네", 5: "다섯", 6: "여섯",
    7: "일곱", 8: "여덟", 9: "아홉", 10: "열", 11: "열한", 12: "열두",
}

# 월 읽기 불규칙 (유월/시월)
_MONTH_SPECIAL = {6: "유", 10: "시"}

_ALPHABET = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프",
    "G": "지", "H": "에이치", "I": "아이", "J": "제이", "K": "케이",
    "L": "엘", "M": "엠", "N": "엔", "O": "오", "P": "피", "Q": "큐",
    "R": "알", "S": "에스", "T": "티", "U": "유", "V": "브이",
    "W": "더블유", "X": "엑스", "Y": "와이", "Z": "제트",
}


def read_sino(n: int) -> str:
    """정수를 한자어 수사로 읽는다. 15000 -> '만 오천', 0 -> '영'."""
    if n < 0:
        return "마이너스 " + read_sino(-n)
    if n == 0:
        return "영"
    groups: list[int] = []
    while n:
        groups.append(n % 10000)
        n //= 10000
    parts: list[str] = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if not g:
            continue
        body = _read_group(g)
        # '일만'은 '만'으로 줄여 읽는 것이 관례. '일억/일조'는 '일'을 유지한다.
        if i == 1 and g == 1:
            body = ""
        parts.append(body + _BIG_UNITS[i])
    return " ".join(p for p in parts if p)


def _read_group(g: int) -> str:
    s = ""
    for exp, unit in ((3, "천"), (2, "백"), (1, "십")):
        d = (g // 10**exp) % 10
        if d:
            s += ("" if d == 1 else _SINO[d]) + unit
    d = g % 10
    if d:
        s += _SINO[d]
    return s


def read_digits(digits: str) -> str:
    """자릿수 그대로 읽기. '1588' -> '일오팔팔', 0은 '공'."""
    return "".join(_DIGIT_NAMES[int(c)] for c in digits if c.isdigit())


def read_hour(hour: int) -> str:
    """시각의 '시' 앞 숫자를 고유어로 읽는다. 13~24시는 오후로 환산한다."""
    meridiem = ""
    if hour == 0:
        return "밤 열두"
    if hour > 12:
        hour -= 12
        meridiem = "오후 "
    return meridiem + _NATIVE_HOURS[hour]


def _normalize_phone(text: str) -> str:
    # 02-1234-5678 / 1588-1234 / 010-1234-5678 형태.
    # 하이픈 자리는 쉼표로 바꿔 자연스러운 끊어읽기를 유도한다.
    def repl(m: re.Match) -> str:
        groups = [g for g in m.groups() if g]
        return ", ".join(read_digits(g) for g in groups)

    # 한글은 \b 기준 단어 문자라서 '5432로'처럼 조사가 붙으면 \b가 실패한다.
    # 숫자 경계는 (?<!\d) / (?!\d)로 직접 지정한다.
    return re.sub(r"(?<![\d-])(\d{2,4})-(\d{3,4})(?:-(\d{4}))?(?![\d-])", repl, text)


def _normalize_time(text: str) -> str:
    # 09:30 / 18시 / 9시 30분 / 오후 3시
    # 텍스트에 이미 오전/오후가 있으면 read_hour가 덧붙이는 '오후'를 제거한다.
    def hour_text(hour: int, has_meridiem: bool) -> str:
        out = read_hour(hour)
        if has_meridiem and out.startswith("오후 "):
            out = out[len("오후 "):]
        return out

    def repl_colon(m: re.Match) -> str:
        meridiem, hour, minute = m.group(1), int(m.group(2)), int(m.group(3))
        if hour > 24 or minute > 59:
            return m.group(0)
        out = (meridiem + " " if meridiem else "") + hour_text(hour, bool(meridiem)) + " 시"
        if minute:
            out += " " + read_sino(minute) + " 분"
        return out

    text = re.sub(r"(?:(오전|오후)\s*)?(?<!\d)(\d{1,2}):(\d{2})(?!\d)", repl_colon, text)

    def repl_si(m: re.Match) -> str:
        meridiem, hour = m.group(1), int(m.group(2))
        if hour > 24:
            return m.group(0)
        return (meridiem + " " if meridiem else "") + hour_text(hour, bool(meridiem)) + " 시"

    # '시간'은 시각이 아니므로 제외 ('18시까지'는 시각이다)
    return re.sub(r"(?:(오전|오후)\s*)?(?<!\d)(\d{1,2})\s*시(?!간)", repl_si, text)


def _normalize_date(text: str) -> str:
    def repl_month(m: re.Match) -> str:
        month = int(m.group(1))
        if not 1 <= month <= 12:
            return m.group(0)
        body = _MONTH_SPECIAL.get(month) or read_sino(month)
        return body + "월"

    text = re.sub(r"\b(\d{1,2})\s*월", repl_month, text)
    text = re.sub(r"\b(\d{1,2})\s*일(?![가-힣])", lambda m: read_sino(int(m.group(1))) + " 일", text)
    text = re.sub(r"\b(\d{4})\s*년", lambda m: read_sino(int(m.group(1))) + " 년", text)
    return text


def _strip_thousands_commas(text: str) -> str:
    # 15,000 -> 15000 (숫자 그룹 콤마만 제거, 나열 쉼표는 유지)
    while True:
        new = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", text)
        if new == text:
            return new
        text = new


def _normalize_percent(text: str) -> str:
    return re.sub(r"(\d+(?:\.\d+)?)\s*%", lambda m: _read_number_token(m.group(1)) + " 퍼센트", text)


def _read_number_token(token: str) -> str:
    if "." in token:
        whole, frac = token.split(".", 1)
        return read_sino(int(whole)) + " 점 " + " ".join(_DIGIT_NAMES[int(c)] for c in frac)
    return read_sino(int(token))


def _normalize_numbers(text: str) -> str:
    return re.sub(r"\d+(?:\.\d+)?", lambda m: _read_number_token(m.group(0)), text)


def _normalize_acronyms(text: str) -> str:
    # 2글자 이상 연속 대문자는 철자 읽기 (ARS -> 에이알에스)
    return re.sub(
        r"\b[A-Z]{2,}\b",
        lambda m: "".join(_ALPHABET[c] for c in m.group(0)),
        text,
    )


def normalize(text: str) -> str:
    """ARS 낭독용으로 텍스트 전체를 발음 한글로 정규화한다."""
    text = _strip_thousands_commas(text)
    text = _normalize_phone(text)
    text = _normalize_time(text)
    text = _normalize_date(text)
    text = _normalize_percent(text)
    text = _normalize_numbers(text)
    text = _normalize_acronyms(text)
    # 기호 정리
    text = text.replace("%", " 퍼센트").replace("&", " 앤 ").replace("~", "에서 ")
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()
