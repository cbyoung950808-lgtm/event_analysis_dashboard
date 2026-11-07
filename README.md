# Streamlit Cloud 배포 구성

이 폴더의 **내용물**을 GitHub 저장소 최상위에 올립니다. 상위 실습 폴더 전체를 올리지 않습니다.
원본을 수정하지 않고 생성한 최소 실행 묶음이며, 외부 업로드는 수행하지 않았습니다.

## Cloud에 입력할 값

- Main file path: `streamlit_app.py`
- Advanced settings → Python version: **3.12** (직접 선택)
- Branch: 실제 업로드한 브랜치
- Secrets: 현재 앱은 별도 키가 필요하지 않음

`.python-version`은 로컬 환경 안내용입니다. Cloud의 Python 버전 선택을 대신하지 않습니다.

## 포함 파일

```text
streamlit_app.py
requirements.txt
.python-version
.gitignore
.streamlit/config.toml
analysis/                 # 실제 대시보드가 import하는 모듈만 포함
data/SOURCE.txt
data/processed/events_clean.csv.gz
data/processed/events_with_category.csv.gz.part001
data/processed/events_with_category.csv.gz.part002
data/processed/events_with_category.csv.gz.parts.json
cloud_manifest.json       # 파일 크기와 압축 해제 내용 SHA-256
```

## 점검 결과

- 실행 위치는 저장소 루트이며, 데이터 경로는 앱 파일 위치를 기준으로 해석합니다.
- CSV 원본이 없으면 `.csv.gz`를 자동으로 읽습니다. gzip은 무손실 압축이며 두 입력의 압축 해제 SHA-256을 검증했습니다.
- 압축 전 CSV는 각각 약 161MiB·206MiB로 일반 GitHub 파일 제한을 초과합니다. 압축본은 모두 100MiB 미만입니다.
- GitHub 웹 업로드 제한은 파일당 25MiB입니다. 이를 넘는 압축본은 GitHub Desktop 또는 Git으로 올리세요. ZIP 파일 자체를 저장소에 올리는 방식은 앱 배포가 아닙니다.
- 라이브러리는 검증 환경의 버전으로 고정했습니다. 런타임에서 직접 쓰는 NumPy·Jinja2도 선언했습니다.
- 로컬 가상환경, macOS Python 실행 파일, 원본 CSV, 방문자 CSV, 출력 이미지·표, 비밀 파일은 포함하지 않았습니다.
- 실시간 앱은 별도 macOS 폰트나 시스템 패키지를 요구하지 않습니다. Matplotlib은 오프라인 분석에서만 사용하므로 Cloud 의존성에서 제외했습니다.
- 새 데이터 또는 코드로 다시 배포할 때는 상위 프로젝트에서 `analysis/prepare_cloud.py`를 재실행해 묶음을 갱신합니다.

## 남아 있는 확인 사항

대상 저장소: https://github.com/cbyoung950808-lgtm/event_analysis_dashboard
GitHub 업로드와 Cloud에서의 실제 배포는 별도 절차입니다.
선택한 탭만 계산·표시하도록 지연 실행을 적용했습니다. 대용량 데이터를 집계하므로 첫 실행·기간 변경에는 시간이 걸릴 수 있습니다.
압축은 전송 크기를 줄이며 실행 메모리를 줄이지는 않습니다. Cloud 계정의 실제 CPU·메모리 제한과 동시 접속 성능은 배포 후 로그에서 확인해야 합니다.
자원 부족이 발생하면 데이터 로딩 통합, 탭별 지연 계산, 캐시 축소 또는 집계 데이터 사전 생성이 다음 개선 후보입니다.

## 데이터 출처와 이용 조건

`data/SOURCE.txt`는 원본 events 데이터의 출처·라이선스 기록입니다. 원본 events를 기간 제한·중복 제거하고 날짜 열을 추가했으며, 카테고리 이력을 시점 기준 왼쪽 조인했습니다.
Retailrocket / Roman Zykov의 Kaggle 데이터이며, 기록된 라이선스는 CC BY-NC-SA 4.0입니다. 교육·비상업적 이용과 출처 표시 조건을 유지하세요.
카테고리 보조 파일의 별도 출처·허가 기록은 제공되지 않았으므로, 공개 배포 전에 해당 파일의 이용 조건도 확인해야 합니다.

## 공식 문서

- [파일 구성](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization)
- [배포와 Python 버전 선택](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [앱 자원과 제한](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)
- [GitHub 파일 크기 제한](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)

## 로컬 검증 결과

Python 3.12의 별도 환경에서 Matplotlib 없이 압축 CSV만 사용해 모든 화면과 주요 지표를 확인했습니다.
선택 탭만 계산하도록 적용했지만 모든 탭을 방문한 테스트의 메모리 최대치는 약 2.49GiB였습니다.
Cloud의 실제 자원 한도에 따라 부족할 수 있으므로 배포 성공·동시 접속 성능을 보장하는 결과는 아닙니다.
자세한 검증 환경과 한계는 `verification.json`을 확인하세요.

대용량 gzip의 두 조각은 실행 시 임시 폴더에 복원되며 각 조각과 복원본의 SHA-256을 검증합니다. CSV 내용은 동일합니다.
