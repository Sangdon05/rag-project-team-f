# NEO-RETRO 에셋 출처와 이용 제한

관동도감 대화 화면에 사용하는 에셋의 출처와 라이선스입니다.

| 에셋 | 위치 | 출처 | 이용 제한 |
| --- | --- | --- | --- |
| 포켓몬 스프라이트 151종 (64×64) | `sprites/{도감번호}.png` | [PokeAPI/sprites](https://github.com/PokeAPI/sprites) `sprites/pokemon/versions/generation-iii/firered-leafgreen/` (2026-11-26 확보) | 저장소는 CC0이지만 저장소 LICENCE에 따라 **이미지 저작권은 The Pokémon Company**에 있습니다. 로컬 시연·학습용으로만 쓰고, 외부 공개·배포 전에 이용 가능 여부를 확인해야 합니다. |
| 스프라이트 기준선 정보 | `sprites/manifest.json` | 각 PNG의 불투명 영역(bbox)을 계산한 기준선 정보 | 자체 생성 |
| 메이트 픽셀 초상 3종 (40×40) | `mates/{jiwoo,iseul,woong}-pixel.png` | 포켓몬 애니메이션 인물 그림을 잘라 축소·색 제한한 픽셀 이미지 | 원본 이미지의 저작권은 해당 권리자에게 있습니다. 원본과 같은 이용 제한을 따릅니다. |
| 픽셀 폰트 Galmuri11, Galmuri11 Bold | `fonts/Galmuri11*.woff2` | npm `galmuri@2.40.3` | SIL Open Font License 1.1. [라이선스 전문](fonts/OFL-Galmuri.md) |
| 본문 폰트 Pretendard Variable | `fonts/PretendardVariable.woff2` | npm `pretendard@1.3.9` | SIL Open Font License 1.1. [라이선스 전문](fonts/LICENSE-Pretendard.txt) |

- 스프라이트는 FireRed/LeafGreen(관동 리메이크)의 그림을 **화면 표현에만** 씁니다. 도감 수치·타입·기술·상성 규칙은 기존과 같이 `data/processed`의 1세대 Red/Blue 값을 씁니다.
- 151종 그림을 새로 그리지 않았습니다. 하늘·구름·초원 배경은 SVG 픽셀 그래픽입니다.
