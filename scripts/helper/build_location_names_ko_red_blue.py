#!/usr/bin/env python3
"""Red·Blue 장소 식별자 → 한국어판 공식 장소명 대응표를 만든다 (사용자 승인 반영).

입력: data/processed/encounters_red_blue.json (location·location_area),
      data/processed/machine_acquisition_red_blue.json (map_id_raw)
출력: data/processed/location_names_ko_red_blue.json (HASHES 대상 아님)

사용법:
    uv run python scripts/helper/build_location_names_ko_red_blue.py          # 출력 파일을 덮어쓴다
    uv run python scripts/helper/build_location_names_ko_red_blue.py --check  # 저장된 JSON과 다르면 종료 코드 1

- 식별자 목록은 입력 파일에서 뽑는다. 아래 PARENTS·규칙표는 2026-11-24에 출처 문서(고정 revid)를 직접 읽고 옮긴
  조사 결과이며, 생성기는 네트워크를 쓰지 않는다. 규칙표로 풀 수 없는 식별자가 나오면 오류로 멈춘다.
- 출처에서 확인하지 못한 한국어명은 만들지 않고 null로 둔다. 층·방·구역 수식어는 팀이 붙인 것이므로 composed로 표시한다.
- 실행 시각 같은 가변 값을 넣지 않는다. 출력은 LF, 키 정렬, 항목은 (종류, 식별자) 순서다.
- 사용자 승인(REVIEW): 전체 항목을 제안된 이름 그대로 승인했다(uncertain·composed 포함). 홍련섬/홍련마을은 '홍련섬'으로
  사용자가 결정했다. 승인은 review_status만 바꾸며 confidence(출처 확신도)는 바꾸지 않는다.
"""

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENCOUNTERS_PATH = "data/processed/encounters_red_blue.json"
ACQUISITION_PATH = "data/processed/machine_acquisition_red_blue.json"
OUTPUT_PATH = "data/processed/location_names_ko_red_blue.json"
SCHEMA_VERSION = 1
CHECKED_ON = "2026-11-24"
KINDS = ("pokeapi_location", "pokeapi_location_area", "pokered_map")
REVIEW_STATUSES = ("pending", "approved", "rejected")
APPROVED = "approved"
# 사용자 검토 결과. 이름을 바꾸거나 항목을 빼면 이 기록과 entries를 함께 고친다.
REVIEW = {
    "approved_by": "user",
    "approved_on": CHECKED_ON,
    "decisions": [
        "cinnabar-island: Bulbapedia·포켓몬 위키의 '홍련섬'·'홍련마을' 중 '홍련섬'으로 확정 (사용자 결정)",
        "그 밖의 항목: 제안된 name_ko를 그대로 승인 (confidence uncertain·composition composed 항목 포함)",
    ],
    "note": "승인은 review_status만 바꾼다. confidence는 출처 확신도이며 사용자 승인과 별개라 바꾸지 않았다.",
    "scope": "전체 entries (홍련섬 결정 포함)",
    "status": APPROVED,
}

GAME_LABELS = {"HGSS": "하트골드·소울실버 한국어판", "LPLE": "레츠고! 피카츄·레츠고! 이브이 한국어판"}
NO_GAME = "출처가 게임을 특정하지 않음"


def bulba(title, revid):
    url = "https://bulbapedia.bulbagarden.net/w/index.php?" + urllib.parse.urlencode(
        {"title": title.replace(" ", "_"), "oldid": revid})
    return {"site": "bulbapedia", "title": title, "revid": revid, "url": url}


def kowiki(title, revid):
    url = ("https://pokemon.fandom.com/ko/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe="/()")
           + f"?oldid={revid}")
    return {"site": "pokemon_fandom_ko", "title": title, "revid": revid, "url": url}


def parent(name_en, name_ko, confidence, sources, games=(), note=""):
    return {"name_en": name_en, "name_ko": name_ko, "confidence": confidence, "sources": sources,
            "game_basis": [GAME_LABELS[g] for g in games] or [NO_GAME], "note": note}


HL = ("HGSS", "LPLE")
ROUTE_REVIDS = {1: 314397, 2: 314401, 3: 314403, 4: 325880, 5: 314408, 6: 314409, 7: 314420, 8: 314418,
                9: 314413, 10: 314414, 11: 314412, 12: 314433, 13: 314432, 14: 314431, 15: 314430, 16: 314422,
                17: 314423, 18: 314424, 19: 314426, 20: 314427, 21: 309927, 22: 314435, 23: 314434, 24: 314406,
                25: 314407}


def route_parent(n):
    sea = n in (19, 20, 21)
    name_ko = f"{n}번수로" if sea else f"{n}번도로"
    title = name_ko if n in (24, 25) else f"관동 {name_ko}"
    return parent(f"Route {n}", name_ko, "confirmed", [kowiki(title, ROUTE_REVIDS[n])],
                  ("LPLE",) if n == 23 else HL, "포켓몬 위키 정보상자 이름·영칭(Route N)으로 확인")


# 조사 결과: 상위 장소의 한국어 공식명과 근거. confirmed = 출처의 장소 이름 항목에서 직접 확인, 다른 출처와 표기 일치.
# uncertain = 출처끼리 표기가 다르거나(띄어쓰기 포함), 영문명 대응을 간접적으로만 확인.
PARENTS = {
    "pallet-town": parent("Pallet Town", "태초마을", "confirmed",
                          [bulba("Pallet Town", 4672858), kowiki("태초마을", 332951)], HL),
    "viridian-city": parent("Viridian City", "상록시티", "confirmed",
                            [bulba("Viridian City", 4662287), kowiki("상록시티", 314398)], HL),
    "pewter-city": parent("Pewter City", "회색시티", "confirmed",
                          [bulba("Pewter City", 4664734), kowiki("회색시티", 332952)], HL),
    "cerulean-city": parent("Cerulean City", "블루시티", "confirmed",
                            [bulba("Cerulean City", 4666219), kowiki("블루시티", 314405)], HL),
    "vermilion-city": parent("Vermilion City", "갈색시티", "confirmed",
                             [bulba("Vermilion City", 4664726), kowiki("갈색시티", 314410)], HL),
    "celadon-city": parent("Celadon City", "무지개시티", "confirmed",
                           [bulba("Celadon City", 4663334), kowiki("무지개시티", 314421)], HL),
    "fuchsia-city": parent("Fuchsia City", "연분홍시티", "confirmed",
                           [bulba("Fuchsia City", 4664724), kowiki("연분홍시티", 314425)], HL),
    "saffron-city": parent("Saffron City", "노랑시티", "confirmed",
                           [bulba("Saffron City", 4664737), kowiki("노랑시티", 314419)], HL),
    "cinnabar-island": parent("Cinnabar Island", "홍련섬", "uncertain",
                              [bulba("Cinnabar Island", 4670930), kowiki("홍련마을", 314428)], HL,
                              "Bulbapedia는 홍련섬·홍련마을 두 이름을, 포켓몬 위키는 '홍련마을 (홍련섬)'을 적는다. "
                              "게임별 표기 차이일 수 있다. 사용자 결정: '홍련섬'으로 확정"),
    **{f"route-{n}": route_parent(n) for n in range(1, 26)},
    "safari-zone": parent("Safari Zone", "사파리존", "uncertain",
                          [bulba("Kanto Safari Zone", 4663497), kowiki("관동 사파리존", 304415)], (),
                          "Bulbapedia는 '사파리존', 포켓몬 위키 정보상자는 지방 구분을 붙인 '관동 사파리존'"),
    "power-plant": parent("Power Plant", "무인발전소", "confirmed",
                          [kowiki("무인 발전소 (관동)", 314415)], ("LPLE",),
                          "포켓몬 위키 정보상자 이름은 '무인발전소', 문서 제목은 '무인 발전소 (관동)'. "
                          "2세대·하트골드·소울실버의 '발전소'와 다른 장소"),
    "underground-path": parent("Underground Path", "지하통로", "uncertain",
                               [bulba("Underground Path (Kanto Routes 5–6)", 4356867),
                                kowiki("지하통로(5-6번도로)", 303493)], (),
                               "Bulbapedia는 '지하통로', 포켓몬 위키는 '지하통로(5-6번도로)'. PokeAPI 기록(니드런 교환)은 "
                               "포켓몬 위키 설명상 5번도로 쪽 입구"),
    "victory-road": parent("Victory Road", "챔피언로드", "confirmed",
                           [bulba("Victory Road (Kanto)", 4671663), kowiki("챔피언로드/관동", 313120)], HL),
    "mt-moon": parent("Mt. Moon", "달맞이산", "confirmed", [bulba("Mt. Moon", 4663483), kowiki("달맞이산", 314402)], HL),
    "pokemon-mansion": parent("Pokémon Mansion", "포켓몬저택", "confirmed", [kowiki("포켓몬저택/관동", 304078)]),
    "pokemon-tower": parent("Pokémon Tower", "포켓몬타워", "confirmed",
                            [bulba("Pokémon Tower", 4663496), kowiki("포켓몬타워", 274510)], HL),
    "rock-tunnel": parent("Rock Tunnel", "돌산터널", "confirmed", [kowiki("돌산터널", 323135)], HL),
    "seafoam-islands": parent("Seafoam Islands", "쌍둥이섬", "confirmed",
                              [bulba("Seafoam Islands", 4615961), kowiki("쌍둥이섬", 314429)], HL),
    "cerulean-cave": parent("Cerulean Cave", "블루시티동굴", "confirmed",
                            [bulba("Cerulean Cave", 4664758), kowiki("블루시티동굴", 304111)], (),
                            "포켓몬 위키는 1세대(일본판) 명칭이 '이름없는 동굴'이었다고 적는다"),
    "digletts-cave": parent("Diglett's Cave", "디그다의 굴", "confirmed", [kowiki("디그다의 굴", 314411)], HL),
    "viridian-forest": parent("Viridian Forest", "상록숲", "confirmed", [kowiki("상록숲", 314399)], HL),
    "celadon-mansion": parent("Celadon Mansion", "무지개맨션", "confirmed",
                              [bulba("Celadon Condominiums", 4664709), kowiki("무지개맨션", 252687)], (),
                              "두 출처의 현재 영문명은 Celadon Condominiums"),
    "game-corner": parent("Celadon Game Corner", "무지개 게임코너", "uncertain",
                          [bulba("Celadon Game Corner", 4667002), kowiki("무지개 게임코너", 303975)], (),
                          "Bulbapedia는 '로켓 게임코너'와 '무지개 게임 코너'를, 포켓몬 위키는 '무지개 게임코너'를 적는다"),
    "pokemon-lab": parent("Pokémon Lab", "포켓몬 연구소", "uncertain", [kowiki("포켓몬 연구소", 132280)], (),
                          "포켓몬 위키 단문 문서(정보상자·영칭 없음)와 홍련마을 문서의 시설 목록으로만 확인"),
    "fighting-dojo": parent("Fighting Dojo", "격투도장", "confirmed",
                            [bulba("Fighting Dojo", 4664701), kowiki("격투도장", 279864)]),
    "silph-co": parent("Silph Co.", "실프주식회사", "confirmed",
                       [bulba("Silph Co.", 4663494), kowiki("실프주식회사", 304059)], (),
                       "Bulbapedia 회사명 표기 '실프주식회사'(건물은 '실프주식회사 본사 빌딩')"),
    "ss-anne": parent("S.S. Anne", "상트앙느호", "confirmed",
                      [bulba("S.S. Anne", 4663487), kowiki("상트앙느호", 303959)], ("LPLE",),
                      "포켓몬 위키 갈색시티 문서 링크에는 '상트안느호' 표기도 있다"),
    "celadon-dept-store": parent("Celadon Department Store", "무지개 백화점", "uncertain",
                                 [bulba("Celadon Department Store", 4664706), kowiki("무지개 백화점", 309092)], (),
                                 "Bulbapedia는 '무지개백화점'(붙여 씀), 포켓몬 위키는 '무지개 백화점'"),
    "pewter-gym": parent("Pewter Gym", "회색체육관", "confirmed", [kowiki("회색체육관", 272934)]),
    "cerulean-gym": parent("Cerulean Gym", "블루체육관", "confirmed", [kowiki("블루체육관", 309923)]),
    "vermilion-gym": parent("Vermilion Gym", "갈색체육관", "confirmed", [kowiki("갈색체육관", 303077)]),
    "celadon-gym": parent("Celadon Gym", "무지개체육관", "confirmed", [kowiki("무지개체육관", 252730)], HL),
    "fuchsia-gym": parent("Fuchsia Gym", "연분홍체육관", "confirmed", [kowiki("연분홍체육관", 303517)], HL),
    "saffron-gym": parent("Saffron Gym", "노랑체육관", "confirmed", [kowiki("노랑체육관", 273240)]),
    "cinnabar-gym": parent("Cinnabar Gym", "홍련체육관", "confirmed", [kowiki("홍련체육관", 273049)]),
    "viridian-gym": parent("Viridian Gym", "상록체육관", "confirmed", [kowiki("상록체육관", 239752)], ("HGSS",)),
    "rocket-hideout": parent("Rocket Hideout", "로켓단 아지트", "uncertain",
                             [bulba("Team Rocket Hideout", 4663493), kowiki("로켓단 아지트/관동", 318661)], (),
                             "Bulbapedia는 '로켓단아지트'(붙여 씀), 포켓몬 위키 정보상자는 '로켓단 아지트(관동)'. "
                             "괄호 지방 구분은 위키 문서 구분으로 보고 뺐다"),
    "pokemon-center": parent("Pokémon Center", "포켓몬센터", "confirmed",
                             [bulba("Pokémon Center", 4672139), kowiki("포켓몬센터", 337221)], (),
                             "시설 종류 이름"),
    "gate": parent("Gate", "게이트", "confirmed", [bulba("Gate", 4630363), kowiki("게이트", 217074)], (),
                   "시설 종류 이름"),
}

# 상위 장소명 외 수식어의 근거 (출처 본문 서술로 간접 확인 → uncertain)
EXTRA = {
    "vermilion-harbor": ("항구", kowiki("갈색시티", 314410), "포켓몬 위키 갈색시티 문서의 '항구' 절 제목"),
    "ss-anne-captain": ("선장실", kowiki("상트앙느호", 303959), "포켓몬 위키 상트앙느호 문서 본문의 '선장실'"),
    "game-corner-exchange": ("교환소", kowiki("무지개 게임코너", 303975), "포켓몬 위키 무지개 게임코너 문서 본문·표의 '교환소'"),
    "copycat-house": ("흉내내기 아가씨의 집", kowiki("노랑시티", 314419),
                      "포켓몬 위키 노랑시티 문서 시설 목록의 '흉내내기 아가씨의 집' (흉내내기 아가씨 = Copycat)"),
    "psychic-house": ("에스퍼아저씨의 집", kowiki("노랑시티", 314419),
                      "포켓몬 위키 노랑시티 문서 시설 목록의 '에스퍼아저씨의 집' (TM29를 주는 집으로 서술)"),
    "warden-house": ("사파리 원장의 집", kowiki("연분홍시티", 314425),
                     "포켓몬 위키 연분홍시티 문서 시설 목록의 '사파리 원장 (바오바)의 집'"),
}

POKEAPI_LOCATION_PARENT = {
    "kanto-power-plant": "power-plant", "kanto-safari-zone": "safari-zone",
    "kanto-underground-path": "underground-path", "kanto-victory-road-2": "victory-road",
}
DIRECTIONS = {"east": ("동쪽 구역", "East"), "north": ("북쪽 구역", "North"), "west": ("서쪽 구역", "West"),
              "middle": ("중앙 구역", "Middle")}
FLOOR = re.compile(r"^(b?)(\d+)f$", re.IGNORECASE)


def floor_ko(token):
    match = FLOOR.match(token)
    if not match:
        return None
    basement, number = match.groups()
    return (f"지하 {number}층" if basement else f"{number}층"), (f"B{number}F" if basement else f"{number}F")


def location_parent(location):
    if location in POKEAPI_LOCATION_PARENT:
        return POKEAPI_LOCATION_PARENT[location]
    match = re.fullmatch(r"kanto-(?:sea-)?route-(\d+)", location)
    if match:
        return f"route-{int(match.group(1))}"
    if location in PARENTS:
        return location
    raise ValueError(f"상위 장소 규칙이 없는 PokeAPI location: {location}")


# 특수 location_area·pokered 지도: (상위 키 목록, 한국어명 조립 함수 인자, 영문명, EXTRA 키, 비고)
AREA_SPECIAL = {
    "celadon-city-celadon-mansion": (["celadon-mansion"], None, "Celadon Mansion", None, ""),
    "celadon-city-prize-corner": (["game-corner"], "교환소", "Celadon Game Corner prize corner", "game-corner-exchange", ""),
    "cinnabar-island-cinnabar-lab": (["cinnabar-island", "pokemon-lab"], None, "Cinnabar Island Pokémon Lab", None,
                                     "홍련섬 + 포켓몬 연구소를 팀이 이어 붙였다"),
    "kanto-route-2-north-towards-pewter-city": (["route-2", "pewter-city"], "북쪽 ({pewter-city} 방면)",
                                                "Route 2 (north, towards Pewter City)", None, ""),
    "kanto-route-2-south-towards-viridian-city": (["route-2", "viridian-city"], "남쪽 ({viridian-city} 방면)",
                                                  "Route 2 (south, towards Viridian City)", None, ""),
    "kanto-route-3-pokemon-center": (["route-3", "pokemon-center"], None, "Route 3 Pokémon Center", None,
                                     "PokeAPI 구역 이름을 그대로 옮겼다. 4번도로 포켓몬센터 구역과 같은 건물인지 확인하지 않았다"),
    "kanto-route-4-pokemon-center": (["route-4", "pokemon-center"], None, "Route 4 Pokémon Center", None,
                                     "PokeAPI 구역 이름을 그대로 옮겼다"),
    "saffron-city-fighting-dojo": (["fighting-dojo"], None, "Fighting Dojo", None, ""),
    "saffron-city-silph-co-7f": (["silph-co"], "7층", "Silph Co. 7F", None, ""),
    "vermilion-city-ss-anne-dock": (["vermilion-city"], "항구", "Vermilion City S.S. Anne dock", "vermilion-harbor", ""),
}
MAP_SPECIAL = {
    "CeladonMartRoof": (["celadon-dept-store"], "옥상", "Celadon Department Store rooftop", None, ""),
    "CinnabarLabMetronomeRoom": (["cinnabar-island", "pokemon-lab"], None, "Cinnabar Island Pokémon Lab (Metronome room)",
                                 None, "방 구분(MetronomeRoom)은 한국어 명칭을 확인하지 못해 뺐다"),
    "CopycatsHouse2F": (["saffron-city"], "흉내내기 아가씨의 집 2층", "Copycat's house 2F", "copycat-house", ""),
    "GameCornerPrizeRoom": (["game-corner"], "교환소", "Celadon Game Corner prize room", "game-corner-exchange", ""),
    "MrPsychicsHouse": (["saffron-city"], "에스퍼아저씨의 집", "Mr. Psychic's house", "psychic-house", ""),
    "Route12Gate2F": (["route-12", "gate"], "2층", "Route 12 gate 2F", None, ""),
    "Route16FlyHouse": (["route-16"], "의 집", "Route 16 house (HM02)", None,
                        "건물 고유 이름을 확인하지 못해 '집'만 붙였다"),
    "Route2Gate": (["route-2", "gate"], None, "Route 2 gate", None, ""),
    "SSAnne1FRooms": (["ss-anne"], "1층 객실", "S.S. Anne 1F rooms", None, ""),
    "SSAnneB1FRooms": (["ss-anne"], "지하 1층 객실", "S.S. Anne B1F rooms", None, ""),
    "SSAnneCaptainsRoom": (["ss-anne"], "선장실", "S.S. Anne captain's room", "ss-anne-captain", ""),
    "SafariZoneEast": (["safari-zone"], "동쪽 구역", "Safari Zone East", None, ""),
    "SafariZoneNorth": (["safari-zone"], "북쪽 구역", "Safari Zone North", None, ""),
    "SafariZoneWest": (["safari-zone"], "서쪽 구역", "Safari Zone West", None, ""),
    "SafariZoneSecretHouse": (["safari-zone"], "안의 집", "Safari Zone secret house", None,
                              "건물 고유 이름을 확인하지 못해 '안의 집'만 붙였다"),
    "WardensHouse": (["fuchsia-city"], "사파리 원장의 집", "Warden's house", "warden-house", ""),
}
# 상위 장소명은 확인됐지만 식별자가 가리키는 건물·구역 자체를 확인하지 못한 항목 (confidence를 uncertain으로 둔다)
FORCE_UNCERTAIN = {
    "kanto-route-3-pokemon-center": "PokeAPI에 3번도로·4번도로 포켓몬센터 구역이 따로 있으나 실제 건물 구분을 확인하지 않았다",
    "Route16FlyHouse": "건물 고유 이름 미확인",
    "SafariZoneSecretHouse": "건물 고유 이름 미확인",
}
MAP_PREFIX = {
    "MtMoon": "mt-moon", "PokemonMansion": "pokemon-mansion", "RocketHideout": "rocket-hideout",
    "SilphCo": "silph-co", "VictoryRoad": "victory-road", "CeladonMart": "celadon-dept-store",
}
MAP_WHOLE = {"CeladonCity": "celadon-city", "CeruleanCity": "cerulean-city", "ViridianCity": "viridian-city",
             "PowerPlant": "power-plant"}


class LocationNameError(ValueError):
    """식별자를 대응표 규칙으로 풀 수 없다."""


def load_json(relpath):
    return json.loads((ROOT / relpath).read_text(encoding="utf-8"))


def collect_identifiers():
    """입력 파일에서 (종류, 식별자, 추가 정보) 목록을 뽑는다."""
    encounters = load_json(ENCOUNTERS_PATH)
    locations, areas = {}, {}
    for pokemon in encounters["pokemon"]:
        for version in encounters["versions"]:
            for item in pokemon["versions"][version]["encounters"]:
                locations[item["location"]["name"]] = item["location"]["url"]
                areas[item["location_area"]["name"]] = (item["location"]["name"], item["location_area"]["url"])
    maps = {}
    for machine in load_json(ACQUISITION_PATH)["machines"]:
        for location in machine["locations"]:
            maps.setdefault(location["map_id_raw"], set()).add(machine["code"])
    return locations, areas, {key: sorted(value) for key, value in maps.items()}


def compose(parent_keys, modifier, extra_key, name_en, note, identifier):
    parents = [PARENTS[key] for key in parent_keys]
    sources = [source for p in parents for source in p["sources"]]
    notes = [p["note"] for p in parents if p["note"]]
    confidence = "uncertain" if any(p["confidence"] == "uncertain" for p in parents) else "confirmed"
    if extra_key:
        _, source, extra_note = EXTRA[extra_key]
        sources.append(source)
        notes.append(extra_note)
        confidence = "uncertain"
    referenced = set(re.findall(r"\{([a-z0-9-]+)\}", modifier or ""))
    base_keys = [key for key in parent_keys if key not in referenced]
    base = " ".join(PARENTS[key]["name_ko"] for key in base_keys)
    if modifier:
        modifier = modifier.format(**{key: PARENTS[key]["name_ko"] for key in referenced})
    name_ko = (base + modifier if modifier.startswith("의 ") else f"{base} {modifier}") if modifier else base
    composition = "official" if len(base_keys) == 1 and not modifier else "composed"
    if composition == "composed":
        added = [m for m in [modifier] if m] + (["상위 장소명 연결"] if len(base_keys) > 1 else [])
        notes.insert(0, f"공식 상위 장소명 + 팀이 붙인 수식어({', '.join(added)})")
    if note:
        notes.append(note)
    games = []
    for p in parents:
        for game in p["game_basis"]:
            if game not in games and game != NO_GAME:
                games.append(game)
    seen, unique_sources = set(), []
    for source in sources:
        if source["url"] not in seen:
            seen.add(source["url"])
            unique_sources.append(source)
    return {
        "composition": composition,
        "confidence": confidence,
        "game_basis": games or [NO_GAME],
        "name_en": name_en,
        "name_ko": name_ko,
        "note": " / ".join(notes),
        "parent_keys": list(parent_keys),
        "sources": unique_sources,
    }


def resolve_area(area, location):
    if area in AREA_SPECIAL:
        keys, modifier, name_en, extra, note = AREA_SPECIAL[area]
        return compose(keys, modifier, extra, name_en, note, area)
    parent_key = location_parent(location)
    suffix = area[len(location) + 1:] if area.startswith(location + "-") else None
    if suffix == "area":
        return compose([parent_key], None, None, PARENTS[parent_key]["name_en"], "", area)
    floor = floor_ko(suffix) if suffix else None
    if floor:
        ko, en = floor
        return compose([parent_key], ko, None, f"{PARENTS[parent_key]['name_en']} {en}", "", area)
    match = re.fullmatch(r"(?:area-\d+-)?(east|north|west|middle)", suffix or "")
    if parent_key == "safari-zone" and match:
        ko, en = DIRECTIONS[match.group(1)]
        return compose([parent_key], ko, None, f"Safari Zone {en}", f"PokeAPI 구역 이름: {suffix}", area)
    raise LocationNameError(f"규칙이 없는 location_area: {area}")


def resolve_map(map_id):
    if map_id in MAP_SPECIAL:
        keys, modifier, name_en, extra, note = MAP_SPECIAL[map_id]
        return compose(keys, modifier, extra, name_en, note, map_id)
    if map_id in MAP_WHOLE:
        key = MAP_WHOLE[map_id]
        return compose([key], None, None, PARENTS[key]["name_en"], "", map_id)
    match = re.fullmatch(r"Route(\d+)", map_id)
    if match:
        key = f"route-{int(match.group(1))}"
        return compose([key], None, None, PARENTS[key]["name_en"], "", map_id)
    match = re.fullmatch(r"(Pewter|Cerulean|Vermilion|Celadon|Fuchsia|Saffron|Cinnabar|Viridian)Gym", map_id)
    if match:
        key = f"{match.group(1).lower()}-gym"
        return compose([key], None, None, PARENTS[key]["name_en"], "", map_id)
    for prefix, key in MAP_PREFIX.items():
        floor = floor_ko(map_id[len(prefix):]) if map_id.startswith(prefix) else None
        if floor:
            ko, en = floor
            return compose([key], ko, None, f"{PARENTS[key]['name_en']} {en}", "", map_id)
    raise LocationNameError(f"규칙이 없는 pokered 지도: {map_id}")


def entry(kind, identifier, resolved, extra):
    if identifier in FORCE_UNCERTAIN and resolved["confidence"] == "confirmed":
        resolved = {**resolved, "confidence": "uncertain",
                    "note": resolved["note"] + " / uncertain 사유: " + FORCE_UNCERTAIN[identifier]}
    record = {"id": f"{kind}:{identifier}", "identifier": identifier, "identifier_kind": kind,
              "review_status": REVIEW["status"], **resolved, **extra}
    if not record["name_ko"]:
        record.update({"name_ko": None, "composition": None, "confidence": None})
    return record


def build_document():
    locations, areas, maps = collect_identifiers()
    entries = []
    for location, url in sorted(locations.items()):
        key = location_parent(location)
        resolved = compose([key], None, None, PARENTS[key]["name_en"], "", location)
        entries.append(entry("pokeapi_location", location, resolved, {"pokeapi_url": url}))
    for area, (location, url) in sorted(areas.items()):
        entries.append(entry("pokeapi_location_area", area, resolve_area(area, location),
                             {"pokeapi_location": location, "pokeapi_url": url}))
    for map_id, codes in sorted(maps.items()):
        entries.append(entry("pokered_map", map_id, resolve_map(map_id), {"machine_codes": codes}))
    ids = [e["id"] for e in entries]
    if len(ids) != len(set(ids)):
        raise LocationNameError("중복 식별자")
    for e in entries:
        if e["name_ko"] is not None and not e["sources"]:
            raise LocationNameError(f"출처 없는 한국어명: {e['id']}")
    summary = {
        "by_kind": {kind: sum(1 for e in entries if e["identifier_kind"] == kind) for kind in KINDS},
        "composition": {value: sum(1 for e in entries if e["composition"] == value) for value in ("official", "composed")},
        "confidence": {value: sum(1 for e in entries if e["confidence"] == value) for value in ("confirmed", "uncertain")},
        "name_ko_null": sum(1 for e in entries if e["name_ko"] is None),
        "total": len(entries),
    }
    inputs = [{"path": path, "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
              for path in (ENCOUNTERS_PATH, ACQUISITION_PATH)]
    return {
        "description": "영문 Red·Blue 장소 식별자(PokeAPI location·location_area, pokered 지도 ID)와 한국어판 공식 장소명 대응표.",
        "entries": entries,
        "inputs": inputs,
        "notes": [
            "Red·Blue에는 한국어판이 없다. name_ko는 칸토가 나오는 한국어판 게임(하트골드·소울실버, 레츠고! 피카츄·레츠고! 이브이 등)의 "
            "공식 명칭을 출처 위키에서 확인한 것이며 Red·Blue 원판 표기가 아니다. game_basis는 출처 정보상자의 지도 설명에 "
            "표시된 한국어판 게임으로 간접 판단했고, 출처가 게임을 밝히지 않으면 '출처가 게임을 특정하지 않음'으로 둔다.",
            "PokeAPI location names에는 한국어(ko)가 없어 이 표를 별도로 만들었다.",
            f"출처 문서는 {CHECKED_ON}에 MediaWiki API로 읽었고 URL에 oldid(고정 판)를 붙였다. 원문 스냅샷은 저장하지 않는다.",
            "composition: official = 출처의 장소 이름 그대로, composed = 출처의 상위 장소명에 층·방·구역 수식어를 팀이 붙이거나 "
            "상위 장소명을 이어 붙인 것. composed 수식어는 공식 명칭이 아니다.",
            "confidence: confirmed = 출처의 장소 이름 항목에서 직접 확인했고 다른 출처와 표기가 같다. uncertain = 출처끼리 표기가 "
            "다르거나(띄어쓰기 포함) 본문 서술·절 제목 등으로 간접 확인했다. name_ko가 null이면 둘 다 null이다.",
            "review_status는 사용자 승인 결과다. 사용자가 전체 항목을 제안된 이름 그대로 승인했고(uncertain·composed 포함), "
            "홍련섬/홍련마을은 '홍련섬'으로 결정했다(review 참조). confidence는 출처 확신도이며 승인으로 바꾸지 않는다.",
            "영문명(name_en)은 출처의 영문 장소명에 팀이 층·구역 표기를 붙인 것이며 이 표의 검토 대상이 아니다.",
        ],
        "parents": PARENTS,
        "review": {**REVIEW, "entries_approved": sum(1 for e in entries if e["review_status"] == APPROVED),
                   "entries_total": len(entries)},
        "review_statuses": list(REVIEW_STATUSES),
        "schema_version": SCHEMA_VERSION,
        "summary": summary,
        "terms_of_use": [
            {"license": "CC BY-NC-SA 2.5", "source": "Bulbapedia (bulbapedia.bulbagarden.net)",
             "url": "https://creativecommons.org/licenses/by-nc-sa/2.5/",
             "note": "사이트 rightsinfo 표기. 비영리·저작자 표시·동일 조건 변경 허락."},
            {"license": "CC BY-SA", "source": "포켓몬 위키 (pokemon.fandom.com/ko)", "url": "https://www.fandom.com/licensing",
             "note": "사이트 rightsinfo 표기(버전은 Fandom 라이선스 안내 참조). 저작자 표시·동일 조건 변경 허락."},
            {"license": "권리 별도 확인", "source": "Pokémon 장소명",
             "url": "", "note": "장소명 자체는 Nintendo·Creatures·GAME FREAK·The Pokémon Company의 게임 콘텐츠다. 재배포 조건은 별도 확인한다."},
        ],
    }


def render(document):
    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Red·Blue 장소 식별자 → 한국어판 공식 장소명 대응표")
    parser.add_argument("--output", type=Path, default=ROOT / OUTPUT_PATH)
    parser.add_argument("--check", action="store_true", help="쓰지 않고 출력 파일과 같은지만 확인한다")
    args = parser.parse_args(argv)
    try:
        document = build_document()
    except (LocationNameError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    data = render(document).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    if args.check:
        current = args.output.read_bytes() if args.output.exists() else b""
        same = current == data
        print(("same" if same else "differs") + f" sha256={digest}")
        return 0 if same else 1
    args.output.write_bytes(data)
    print(f"wrote {args.output} entries={document['summary']['total']} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
