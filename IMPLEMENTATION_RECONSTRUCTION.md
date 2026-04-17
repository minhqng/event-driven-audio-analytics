# Implementation Reconstruction Document

Repo được đọc và đối chiếu vào ngày **2026-04-12**.  
Các root status docs hiện khóa narrative ở ngày **2026-04-11**.  
Phiên bản hiện tại của tài liệu này chứa **CHUNK 1**, **CHUNK 2**, **CHUNK 3**, **CHUNK 4**, và **CHUNK 5**:

- **Phase 0**: Khởi động tư duy, khóa ground truth, khóa scope, khóa semantic
- **Phase 1**: Khóa contract v1, dựng runtime spine, dựng fake-event integration spine
- **Phase 2**: Xây dựng ingestion pipeline thật trên metadata/audio thực, claim-check artifacts, và publish `audio.metadata` + `audio.segment.ready`
- **Phase 3**: Xây dựng processing pipeline từ claim-check artifact tới `audio.features`, `system.metrics`, và replay-stable processing state
- **Phase 4**: Xây dựng writer sink vào TimescaleDB với envelope validation, UPSERT semantics, replay-safe metrics, checkpoint, và offset commit ordering
- **Phase 5**: Xây dựng SQL views, Grafana provisioning, deterministic demo inputs, và dashboard evidence path
- **Phase 6**: Xây dựng validation ladder, restart/replay smoke, và bounded evidence generation
- **Phase 7**: Khóa bounded demo path, honest scope, conflict/deferred map, và handoff rules

Tài liệu này được viết cho mục tiêu rất cụ thể: một kỹ sư có thể ngồi xuống, mở repo trống, đọc từng bước, hiểu tại sao hệ thống có hình dạng như hiện tại, và tự tay dựng lại bộ xương đầu tiên mà không phá contract, không phá scope, không overclaim.

## Ghi Chú Về Cách Đánh Số Phase

Trong **`PROJECT_CONTEXT.md`**, execution order lịch sử bắt đầu từ `Phase 1`.  
Để phục vụ giao thức chunking của tài liệu này, tôi chèn thêm **`Phase 0`** như một lớp tiền triển khai:

- `Phase 0` không mâu thuẫn với tài liệu cũ
- `Phase 0` chỉ là tên mới cho phần “khóa sự thật trước khi code”
- `Phase 1` trong tài liệu này tương ứng với phần “shared layer + contract + schema + executable spine” của narrative repo

Nói ngắn: **Phase 0** là “đặt luật chơi”, **Phase 1** là “dựng bộ xương chạy được”.

## Ba Luật Không Được Quên Trong CHUNK 1

1. Kafka chỉ chở event nhỏ; payload nặng phải đi qua claim-check (mẫu thiết kế trong đó event chỉ mang con trỏ tới dữ liệu lớn nằm ở storage ngoài broker).
2. Contract v1 là khóa tích hợp; đổi field name tùy hứng là tự phá khả năng ghép `ingestion`, `processing`, `writer`.
3. Từ ngày đầu tiên phải thiết kế theo hướng at-least-once + idempotent sink (ghi lặp vẫn hội tụ về cùng trạng thái logic), không được viết kiểu “happy path xong rồi tính replay sau”.

# CHUNK 1

## Phase 0. Khởi Động, Khóa Ground Truth, Khóa Semantic

Phase này nhìn bề ngoài giống “đọc tài liệu”, nhưng thực ra đây là lúc bạn khóa mọi thứ mà về sau cực khó sửa:

- project mission
- scope in/out
- audio semantics
- ownership boundary
- contract surface
- build order

Nếu bỏ qua phase này, bạn vẫn viết được code. Nhưng đó sẽ là code “chạy được hôm nay, gãy tích hợp ngày mai”.

---

### Bước 0.1. Dựng Bộ Tài Liệu Ground Truth Trước Khi Viết Code

#### A. Mục tiêu của bước này & tại sao nó đứng đầu?

Mục tiêu là tạo ra một “bộ nhớ ngoài” của dự án trước khi hệ thống có quá nhiều file và quá nhiều ngữ cảnh.  
Trong repo này, bộ nhớ ngoài đó nằm ở các file gốc:

- **`AGENTS.md`**
- **`ARCHITECTURE_CONTRACTS.md`**
- **`IMPLEMENTATION_STATUS.md`**
- **`TASK_BOARD.md`**
- **`PROJECT_CONTEXT.md`**
- **`event-contracts.md`**
- **`REUSE_MAP.md`**
- **`correctness-against-reference.md`**

Lý do nó phải đứng đầu rất đơn giản: nếu không có các file này, “ý định hệ thống” sẽ bị thay thế dần bởi “hành vi tạm thời của code scaffold”.

#### B. Lý thuyết / bản chất đằng sau

Một hệ thống PoC nhỏ nhưng nhiều service luôn có hai lớp sự thật:

```text
T_design = ý định kiến trúc
```

```text
T_runtime = hành vi mà code hiện tại đang biểu diễn
```

Nếu không khóa riêng hai lớp này, đội ngũ sẽ vô tình đồng nhất:

```text
T_design == T_runtime
```

và đó là nguồn gốc của **semantic drift** (trôi nghĩa, tức là hệ thống dần làm thứ khác với thứ ban đầu định chứng minh).

Trong repo này, quy tắc đúng là:

```text
T_authoritative =
- T_design, khi scaffold còn thiếu hoặc code còn drift
- T_runtime, khi cần biết implementation đã đi tới đâu
```

Nói kiểu đời thường: tài liệu gốc trả lời “ta đang cố xây cái gì”, còn code trả lời “ta hiện xây tới đâu rồi”.

#### C. Code Walkthrough: mở file nào, viết gì trước?

Nếu dựng lại từ số 0, hãy tạo ngay các file root guidance với skeleton tối thiểu như sau.

Trong **`AGENTS.md`**, bạn cần ít nhất phần mission, scope, ownership, contract rules:

```md
# AGENTS.md

## Project Mission
- This repo is an academic PoC for event-driven microservices for real-time audio analytics.
- FMA-small is the case-study dataset.
- The old pipeline is the semantic source of truth for audio/DSP logic.

## Scope Boundaries
- In scope: Docker Compose, Kafka KRaft, claim-check, TimescaleDB, Grafana.
- Out of scope: Kubernetes, HA/DR, multi-node Kafka, model serving.

## Rules For Event Contracts
- No raw PCM or large tensors on Kafka.
- Offset commits happen only after successful persistence and checkpoint update.
- Writer must stay idempotent under replay.
```

Trong **`ARCHITECTURE_CONTRACTS.md`**, khóa service boundaries và topic intent:

```md
# ARCHITECTURE_CONTRACTS.md

## Service Boundaries
- ingestion owns metadata ETL, validation, decode/resample, segmentation, artifact writing
- processing owns checksum validation, RMS, silence gate, log-mel, Welford
- writer owns persistence, checkpoints, and offset commits after persistence

## Topic Naming And Ownership
- audio.metadata
- audio.segment.ready
- audio.features
- system.metrics
- audio.dlq
```

Trong **`IMPLEMENTATION_STATUS.md`**, ghi thật rõ cái gì đã chạy thật, cái gì mới reserved:

```md
# IMPLEMENTATION_STATUS.md

## Final Repo State
- Runtime stack is Docker Compose + Kafka KRaft + TimescaleDB + Grafana.
- Event Contract v1 is locked.
- audio.dlq is reserved but not fully modeled as a live runtime path.
```

Trong **`PROJECT_CONTEXT.md`**, khóa build order:

```md
Stable execution order is:
- Phase 1: scope lock, infra bootstrap, reuse audit
- Phase 2: shared layer, event contract, DB schema, fake-event smoke path
- Phase 3: ingestion on real sample data
- Phase 4: processing and feature events
- Phase 5: writer persistence, idempotency, checkpoints
- Phase 6: dashboards and observability
- Phase 7: replay/restart hardening
- Phase 8: benchmark/demo freeze
```

#### D. Why this code/docs exist?

Các file này tồn tại vì repo có hai loại drift rất nguy hiểm:

1. Drift giữa “bài toán muốn chứng minh” và “scaffold code đang có”.
2. Drift giữa Member A và Member B khi hai người làm song song.

Nếu không có file ground truth, mỗi người sẽ định nghĩa project scope theo module mình đang đụng tới. Đó là con đường ngắn nhất để:

- DSP team vô tình đổi output meaning
- infra/persistence team vô tình đổi checkpoint semantics
- dashboard team overclaim thứ DB chưa hề lưu

#### E. Guard & Invariant

Các invariant phải khóa từ đầu:

- `FMA-small` là dataset scope cố định.
- Kafka không chở waveform/tensor lớn.
- Service boundary không được “mượn tạm” trách nhiệm của nhau.
- Replay target là at-least-once + idempotent sink, không phải exactly-once end to end.
- Legacy pipeline là nguồn semantic cho audio correctness, không phải runtime dependency.

Nếu xóa các guard này, lỗi không nổ ngay ở compile time. Nó nổ ở mức tệ hơn: demo vẫn chạy, nhưng thứ bạn demo không còn là project ban đầu nữa.

#### F. Verify & Artifact

Ở bước này, verify là verify bằng mắt và bằng consistency, chưa phải verify bằng broker:

```powershell
Get-Content .\AGENTS.md
Get-Content .\ARCHITECTURE_CONTRACTS.md
Get-Content .\IMPLEMENTATION_STATUS.md
Get-Content .\PROJECT_CONTEXT.md
Get-Content .\event-contracts.md
```

Artifact bạn muốn có sau bước này:

- một bộ root docs đồng thuận với nhau
- build order rõ ràng
- scope in/out rõ ràng
- không còn tranh cãi “repo này đang cố chứng minh cái gì”

---

### Bước 0.2. Khóa Scope PoC và Chặn Overengineering Ngay Từ Đầu

#### A. Mục tiêu của bước này & tại sao nó nằm sau bước 0.1?

Sau khi có ground truth docs, việc tiếp theo là khóa phạm vi PoC để đội ngũ không tự kéo mình vào production fantasy.

Trong repo này, scope được nói cực rõ ở **`AGENTS.md`**, **`PROJECT_CONTEXT.md`**, **`README.md`**, và **`IMPLEMENTATION_STATUS.md`**:

- đây là academic PoC
- bounded evidence quan trọng hơn production completeness
- dashboard phải đọc từ dữ liệu persisted thật
- DLQ, benchmark-scale, persisted Welford là các nhánh còn deferred hoặc reserved

Nó đứng sau bước 0.1 vì scope không thể khóa một cách trung thực nếu chưa biết project mission là gì.

#### B. Lý thuyết / Toán học đằng sau

Hãy coi toàn bộ project là hai tập:

```text
S_in =
{
Compose,
Kafka KRaft,
claim-check,
TimescaleDB,
Grafana,
metadata ETL,
mono 32 kHz,
3.0 s segments,
1.5 s overlap,
RMS,
silence gate,
log-mel summary,
Welford-style stats
}
```

```text
S_out =
{
Kubernetes,
service mesh,
HA/DR,
multi-node Kafka,
exactly-once external DB,
model serving,
training pipelines
}
```

Một PoC tốt không phải là tối đa hóa `|S_in|`.  
Một PoC tốt là tối ưu:

```text
Learning Value * Reproducibility * Honesty
```

chứ không phải tối ưu:

```text
Số lượng buzzword
```

#### C. Code Walkthrough: đọc/viết chỗ nào để khóa scope?

Trong **`README.md`**, hãy viết phần “What This Repository Demonstrates” và “Scope” thật gọn nhưng sắc:

```md
## What This Repository Demonstrates
- Event-driven decoupling across ingestion, processing, and writer
- Claim-check handling for audio segments and run manifests
- At-least-once delivery with checkpoint-aware, idempotent persistence
- Dashboard-backed observability over real persisted PoC data

## Scope
- In scope: Docker Compose, Kafka KRaft, claim-check, TimescaleDB, Grafana
- Out of scope: Kubernetes, service mesh, HA/DR, production object storage/IAM
```

Trong **`IMPLEMENTATION_STATUS.md`**, phải có một section dạng:

```md
## Accepted Limitations
- audio.dlq is reserved but not yet fully modeled
- welford_snapshots exists in SQL but is not produced by processing yet
- default demo path is bounded, not benchmark-scale
```

#### D. Why this code/docs exist?

Các đoạn này tồn tại để chặn hai kiểu bug quản trị:

- **scope creep** (scope tự phình, nghĩa là cứ thêm công nghệ cho “xịn” chứ không tăng giá trị chứng minh)
- **claim inflation** (nói quá năng lực repo, ví dụ nói “production-ready” khi chưa có replay hardening ở scale lớn)

Đây không phải bug syntax. Đây là bug học thuật và bug thuyết trình.

#### E. Guard & Invariant

Invariant:

- Không được dùng dashboard placeholder mà nói như dữ liệu thật.
- Không được viết một storage backend “xịn hơn” rồi phá claim-check path hiện có.
- Không được cài thêm orchestration layer chỉ để nhìn giống kiến trúc cloud-native.

Nếu đảo ngược guard này, Phase 1 sẽ bị kéo lệch hướng: thay vì dựng một spine kiểm chứng được, bạn sẽ dựng một hệ thống trang trí.

#### F. Verify & Artifact

Chạy sanity check cho reader path:

```powershell
Get-Content .\README.md
Get-Content .\docs\README.md
Get-Content .\docs\runbooks\demo.md
Get-Content .\docs\runbooks\validation.md
```

Artifact sau bước này:

- một repo reader path trung thực
- phần “in scope / out of scope” nhìn vào là hiểu ngay
- không ai còn nhầm repo này với một production platform

---

### Bước 0.3. Khóa Audio Semantics Trước Khi Có Business Logic

#### A. Mục tiêu của bước này & tại sao nó ở Phase 0 chứ chưa phải Phase 2/3?

Vì đây là dự án audio analytics. Nếu semantic audio không khóa từ đầu, mọi pipeline phía sau sẽ “đúng cú pháp nhưng sai bài toán”.

Semantic audio phải được coi như contract, không phải implementation detail.

#### B. Lý thuyết / Toán học đằng sau

Repo khóa các thông số sau:

- sample rate đích: `f_s = 32000 Hz`
- segment duration: `T_seg = 3.0 s`
- overlap: `T_overlap = 1.5 s`

Từ đó:

```text
N_seg = f_s * T_seg = 32000 * 3.0 = 96000
```

```text
N_hop = f_s * (T_seg - T_overlap) = 32000 * 1.5 = 48000
```

Log-mel summary target:

```text
shape_mel = (1, 128, 300)
```

Ba con số này không phải “tham số cho đẹp”. Chúng là một phần của **data meaning**.  
Nếu đổi `f_s`, `N_seg`, `N_hop`, hoặc shape log-mel, bạn không còn xử lý cùng một bài toán với legacy reference nữa.

#### C. Code Walkthrough: khóa semantic ở đâu?

Semantic này phải xuất hiện đồng bộ trong tài liệu gốc trước khi business logic thật xuất hiện:

- **`AGENTS.md`**
- **`ARCHITECTURE_CONTRACTS.md`**
- **`PROJECT_CONTEXT.md`**
- **`correctness-against-reference.md`**
- **`REUSE_MAP.md`**

Ví dụ, trong **`AGENTS.md`** nên có block như sau:

```md
For audio logic changes, compare against the reused pipeline semantics:
- subset=small
- mono 32 kHz
- 3.0 s windows
- 1.5 s overlap
- log-mel (1,128,300)
- silence gate
- Welford behavior
```

Trong **`ARCHITECTURE_CONTRACTS.md`** phải có section stable semantics:

```md
## Stable Audio Semantics
- Dataset is FMA-small only
- Decode/resample target is mono / 32 kHz
- Segment duration is 3.0 seconds
- Segment overlap is 1.5 seconds
- Log-mel target shape is (1,128,300)
```

#### D. Why this code/docs exist?

Những dòng này tồn tại vì audio bug nguy hiểm nhất không phải crash. Nó là **silent semantic corruption** (hỏng nghĩa mà không báo lỗi, ví dụ pipeline vẫn chạy nhưng output đã đổi meaning).

Ví dụ rất thật của repo này: downmix order từng drift so với legacy pipeline, làm amplitude mono lệch cỡ `sqrt(2)`. Nếu không khóa semantics ngay ở docs, người sửa sau sẽ không biết tại sao một thay đổi “tối ưu hóa nhỏ” lại phá parity.

#### E. Guard & Invariant

Invariant phải khóa:

- dataset scope luôn là `small`
- mono/32k là normalization target, không phải tùy chọn
- 3.0 s / 1.5 s là segmentation law
- `(1,128,300)` là log-mel semantic target

Xóa invariant này thì hậu quả không dừng ở processing; nó lan sang:

- manifest semantics
- feature payload contract
- dashboard interpretation
- parity narrative với legacy pipeline

#### F. Verify & Artifact

Ở CHUNK 1, verify chủ yếu là verify tính nhất quán tài liệu:

```powershell
Select-String -Path .\AGENTS.md -Pattern "32 kHz|3.0 s|1.5 s|128|300"
Select-String -Path .\ARCHITECTURE_CONTRACTS.md -Pattern "32 kHz|3.0-second|1.5-second|128|300"
Select-String -Path .\PROJECT_CONTEXT.md -Pattern "32 kHz|3.0 s|1.5 s|128|300"
```

Artifact sau bước này:

- semantic constants được khóa ở cấp architecture
- mọi Phase sau có một chuẩn để tự đối chiếu

---

### Bước 0.4. Khóa Service Boundary và Build Order

#### A. Mục tiêu của bước này & tại sao nó là bước cuối của Phase 0?

Sau khi đã khóa mission, scope, và audio semantics, bạn phải khóa nốt ranh giới trách nhiệm.  
Không khóa boundary thì Phase 1 sẽ dựng spine sai chỗ: ví dụ để writer tự decode audio, hoặc để processing tự ghi DB trực tiếp.

#### B. Lý thuyết / bản chất đằng sau

Ranh giới service trong repo này không phải để “cho giống microservices”, mà để tách failure mode:

```text
Ingestion != Processing != Writer
```

vì:

- ingestion thiên về ETL, file I/O, validation
- processing thiên về DSP và checksum correctness
- writer thiên về transaction, idempotency, checkpoint

Build order cũng phải đi theo dependency direction:

```text
Phase 0 -> Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> ...
```

chứ không phải theo cảm hứng “service nào vui thì làm trước”.

#### C. Code Walkthrough: boundary được viết vào đâu?

Trong **`ARCHITECTURE_CONTRACTS.md`**, viết service ownership thật dứt khoát:

```md
## Service Boundaries
- ingestion owns metadata loading, validation, decode/resample, segmentation planning, artifact writing
- processing owns artifact loading, checksum validation, RMS, silence gate, log-mel summary generation
- writer owns persistence, checkpoint updates, and offset commits after successful persistence
```

Trong **`PROJECT_CONTEXT.md`**, khóa build order:

```md
Stable execution order is:
- Phase 1: scope lock, infra bootstrap, reuse audit
- Phase 2: shared layer, event contract, DB schema, fake-event smoke path
- Phase 3: ingestion on real sample data
- Phase 4: processing and feature events
- Phase 5: writer persistence, idempotency, checkpoints
```

#### D. Why this code/docs exist?

Các dòng này tồn tại vì microservice bug lớn nhất lúc đầu không phải network bug. Nó là **responsibility leakage** (rò trách nhiệm, nghĩa là service bắt đầu làm việc của service khác).

Khi boundary rò:

- test không còn biết phải khóa behavior ở đâu
- refactor làm tăng coupling ngầm
- replay reasoning biến thành mớ spaghetti

#### E. Guard & Invariant

Invariant:

- `ingestion` không được tự viết TimescaleDB business rows
- `processing` không được tự định nghĩa lại event contract
- `writer` không được tự decode/featurize audio

Nếu đảo boundary, CHUNK 2, 3, 4 sẽ khó tách riêng để học và khó verify từng lớp một.

#### F. Verify & Artifact

Verify nhanh:

```powershell
Get-Content .\ARCHITECTURE_CONTRACTS.md
Get-Content .\PROJECT_CONTEXT.md
Get-Content .\README.md
```

Artifact sau bước này:

- service map rõ
- build order rõ
- không còn tranh cãi “tại sao Phase này chưa viết processing”

---

## Phase 1. Khóa Contract, Dựng Runtime Spine, Dựng Fake-Event Integration Spine

Đây là phase mà rất nhiều team làm sai. Họ lao thẳng vào ingestion thật hoặc processing thật.  
Repo này đi đường khó hơn nhưng đúng hơn: dựng một bộ xương chạy được, kiểm được, có contract, có schema, có DB surface, có preflight, có smoke path, rồi mới làm business logic nặng.

Bạn có thể xem Phase 1 như việc dựng “cột sống” cho toàn bộ dự án:

- package layout
- dependency slices
- Compose runtime
- Kafka topics
- event envelope + payload models
- JSON schemas + fixtures + contract tests
- DB tables + views
- preflight logic
- fake-event writer smoke

Nếu Phase 1 yếu, về sau bạn sẽ vừa viết logic vừa sửa nền móng. Đó là kiểu mất thời gian đắt nhất.

---

### Bước 1.1. Dựng Python Package và Tách Dependency Theo Vai Trò

#### A. Mục tiêu của bước này & tại sao nó đứng đầu Phase 1?

Mục tiêu là biến repo thành một Python package có thể import được bởi mọi service, đồng thời không ép mọi container phải cài cả thế giới dependency.

Nó đứng đầu Phase 1 vì tất cả các bước sau đều phụ thuộc vào:

- package root thống nhất
- import path ổn định
- dependency slices theo service

#### B. Lý thuyết / Toán học đằng sau

Bạn có thể hình dung dependency footprint của hệ thống là:

```text
D_total
=
D_shared
union
D_ingestion
union
D_processing
union
D_writer
union
D_dev
```

Nhưng mỗi service chỉ nên kéo:

```text
D_service
=
D_shared
union
D_its_own_role
```

Nếu không làm vậy, image:

- to không cần thiết
- build chậm
- conflict dependency tăng
- debugging khó hơn

#### C. Code Walkthrough: viết **`pyproject.toml`**

File trọng tâm là **`pyproject.toml`**:

```toml
[project]
name = "event-driven-audio-analytics"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "confluent-kafka>=2.5.0",
  "numpy>=2.0.0",
  "PyYAML>=6.0.2",
]

[project.optional-dependencies]
ingestion = [
  "av>=14.0.0",
  "polars>=1.0.0",
]
processing = [
  "torch>=2.10.0",
  "torchaudio>=2.10.0",
]
writer = [
  "psycopg[binary]>=3.2.0",
  "psycopg-pool>=3.2.0",
]
dev = [
  "jsonschema>=4.23.0",
  "pytest>=8.3.0",
  "ruff>=0.9.0",
]

[tool.setuptools]
package-dir = {"" = "src"}
```

Giải thích nhanh:

- `confluent-kafka`, `numpy`, `PyYAML` là shared floor
- `av`, `polars` chỉ ingestion cần
- `torch`, `torchaudio` chỉ processing cần
- `psycopg`, `psycopg-pool` chỉ writer cần
- package source nằm dưới `src/` để import path rõ ràng

#### D. Why this code exists?

Block này tồn tại để chống ba lỗi phổ biến:

1. service nào cũng cài `torch` dù không cần
2. import path phụ thuộc “máy em chạy được”
3. test chạy bằng host path bẩn thay vì package boundary rõ ràng

Đặc biệt, việc tách extras ngay từ đầu là một quyết định kiến trúc, không chỉ là tiện lợi packaging.

#### E. Guard & Invariant

Invariant:

- shared code phải đi qua **`src/event_driven_audio_analytics/shared/`**
- dependency nặng không được kéo vào service không dùng
- `pytest` và `jsonschema` là dev tool, không phải runtime dependency của service production path

Nếu vi phạm, Dockerfiles về sau sẽ dần mất vai trò phân tầng.

#### F. Verify & Artifact

Chạy import sanity:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-imports.ps1
```

Hoặc dùng wrapper chính thức:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_event_models.py -q
```

Artifact sau bước này:

- package import được
- dependency layer sạch
- Dockerfile service nào cài đúng extras service đó

---

### Bước 1.2. Dựng Compose Spine Và Tách Container Theo Trách Nhiệm

#### A. Mục tiêu của bước này & tại sao nó đứng ngay sau packaging?

Mục tiêu là dựng runtime substrate nhỏ nhất nhưng đủ thật:

- Kafka KRaft
- TimescaleDB
- Grafana
- `ingestion`
- `processing`
- `writer`
- `pytest`

Nó đứng sau packaging vì container build cần package layout ổn định trước.

#### B. Lý thuyết / bản chất đằng sau

Compose spine là cách repo này vật chất hóa kiến trúc:

```text
Host -> Docker Compose -> Linux containers
```

Quan trọng: host không phải runtime chuẩn của application code.  
Repo này cố tình chọn:

```text
host = orchestrator only
```

để tránh host-specific drift (độ lệch do OS máy người chạy khác nhau).

#### C. Code Walkthrough: viết **`docker-compose.yml`** và Dockerfiles

Trong **`docker-compose.yml`**, block Kafka cần có các ý sau:

```yaml
kafka:
  image: bitnamilegacy/kafka:3.9.0
  environment:
    KAFKA_ENABLE_KRAFT: "yes"
    KAFKA_CFG_AUTO_CREATE_TOPICS_ENABLE: "false"
    KAFKA_CFG_NUM_PARTITIONS: "1"
  healthcheck:
    test: ["CMD-SHELL", "/opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list >/dev/null 2>&1"]
```

Hai dòng đáng nhớ nhất:

```yaml
KAFKA_ENABLE_KRAFT: "yes"
KAFKA_CFG_AUTO_CREATE_TOPICS_ENABLE: "false"
```

`KRaft` là Kafka không phụ thuộc ZooKeeper.  
`auto_create_topics=false` là fail-fast guard: topic nào chưa bootstrap thì phải fail rõ, không được “mọc ra ngầm”.

Block TimescaleDB:

```yaml
timescaledb:
  image: timescale/timescaledb:2.17.2-pg16
  volumes:
    - ./infra/sql:/docker-entrypoint-initdb.d:ro,Z
```

Block Grafana:

```yaml
grafana:
  image: grafana/grafana:11.1.4
  volumes:
    - ./infra/grafana/provisioning:/etc/grafana/provisioning:ro,Z
    - ./infra/grafana/dashboards:/var/lib/grafana/dashboards:ro,Z
```

Block service app:

```yaml
ingestion:
  build:
    context: .
    dockerfile: services/ingestion/Dockerfile
  volumes:
    - ./artifacts:/app/artifacts:z
    - ./tests/fixtures/audio:/app/tests/fixtures/audio:ro,z

processing:
  build:
    context: .
    dockerfile: services/processing/Dockerfile

writer:
  build:
    context: .
    dockerfile: services/writer/Dockerfile
```

Dockerfile **`services/processing/Dockerfile`** cho thấy rất rõ ý tưởng dependency slicing:

```dockerfile
RUN pip install --no-cache-dir \
      --index-url "${PYTORCH_CPU_INDEX_URL}" \
      "torch==${TORCH_CPU_VERSION}" \
      "torchaudio==${TORCHAUDIO_CPU_VERSION}" \
    && sed -i 's/\r$//' /app/services/processing/entrypoint.sh \
    && pip install --no-cache-dir ".[ingestion,processing]"
```

Entry point của service giữ cực mỏng:

```sh
#!/usr/bin/env sh
set -eu

exec python -m event_driven_audio_analytics.processing.app "$@"
```

#### D. Why this code exists?

Mỗi block ở đây sinh ra từ một áp lực rất thật:

- Kafka phải chạy 1-node, 1-partition vì đây là PoC bounded, không phải benchmark cluster
- auto-create topic phải tắt để preflight còn có nghĩa
- SQL init mount vào TimescaleDB để schema là file-truth, không phải click-thủ-công
- Grafana provisioning bằng file để dashboard trở thành artifact versionable
- entrypoint shell mỏng để container chỉ làm một việc: gọi đúng Python module

#### E. Guard & Invariant

Invariant:

- app code chạy trong Linux containers, không dùng host Python làm chuẩn runtime
- `artifacts/` là bind mount chung giữa services
- Grafana và TimescaleDB phải boot được mà không cần click tay
- Kafka healthcheck không đồng nghĩa topic đã tồn tại; topic bootstrap là bước riêng

Nếu bỏ guard “auto-create disabled”, bạn sẽ nhận một hệ thống trông có vẻ tiện hơn nhưng khó debug hơn rất nhiều: service có thể vô tình subscribe/publish lên topic được sinh tự động, sai config mà không ai biết.

#### F. Verify & Artifact

Verify Compose syntax:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-compose.ps1
```

Bootstrap stack:

```powershell
powershell -ExecutionPolicy Bypass -File .\run-demo.ps1
```

Artifact sau bước này:

- containers boot được
- Grafana datasource/dashboard mount được
- TimescaleDB nhận init SQL
- platform spine đã có hình dạng thật

---

### Bước 1.3. Khóa Universe Của Kafka Topics Và Bootstrap Có Chủ Đích

#### A. Mục tiêu của bước này & tại sao nó đến trước contract payload chi tiết?

Mục tiêu là khóa số lượng và tên topic trước, rồi mới khóa field-level contract.  
Nếu topic universe còn lỏng, payload contract chi tiết phía sau sẽ không có chỗ bám ổn định.

#### B. Lý thuyết / Toán học đằng sau

Trong repo này, topic set bị khóa thành:

```text
K =
{
audio.metadata,
audio.segment.ready,
audio.features,
system.metrics,
audio.dlq
}
```

Writer không consume toàn bộ `K`, mà chỉ consume:

```text
K_writer =
{
audio.metadata,
audio.features,
system.metrics
}
```

Đây là một invariant kiến trúc. Nó giúp nói rõ:

- `audio.segment.ready` là handoff cho processing, không phải cho writer
- `audio.dlq` hiện reserved, chưa phải live business path

#### C. Code Walkthrough: viết **`topics.py`** và bootstrap scripts

Trong **`src/event_driven_audio_analytics/shared/contracts/topics.py`**:

```python
AUDIO_METADATA = "audio.metadata"
AUDIO_SEGMENT_READY = "audio.segment.ready"
AUDIO_FEATURES = "audio.features"
SYSTEM_METRICS = "system.metrics"
AUDIO_DLQ = "audio.dlq"

WRITER_INPUT_TOPICS = (
    AUDIO_METADATA,
    AUDIO_FEATURES,
    SYSTEM_METRICS,
)

ALL_TOPICS = (
    AUDIO_METADATA,
    AUDIO_SEGMENT_READY,
    AUDIO_FEATURES,
    SYSTEM_METRICS,
    AUDIO_DLQ,
)
```

Trong **`infra/kafka/create-topics.ps1`**:

```powershell
$topics = @(
    "audio.metadata",
    "audio.segment.ready",
    "audio.features",
    "system.metrics",
    "audio.dlq"
)

foreach ($topic in $topics) {
    docker compose exec -T kafka /opt/bitnami/kafka/bin/kafka-topics.sh `
        --bootstrap-server $bootstrapServer `
        --create `
        --if-not-exists `
        --topic $topic `
        --partitions 1 `
        --replication-factor 1
}
```

Trong **`infra/kafka/create-topics.sh`** cũng mirror y hệt logic đó cho Linux:

```sh
create_topic "audio.metadata"
create_topic "audio.segment.ready"
create_topic "audio.features"
create_topic "system.metrics"
create_topic "audio.dlq"
```

#### D. Why this code exists?

Block này tồn tại vì “topic là public API của hệ thống”.  
Cho Kafka auto-create topic thì tương đương cho public API tự sinh tên endpoint vì typo.

Ngoài ra, việc giữ **`audio.dlq`** trong `ALL_TOPICS` dù chưa fully modeled là một quyết định trung thực:

- nó nói rằng repo biết topic này thuộc planned surface
- nhưng docs vẫn phải nói rõ nó mới reserved

#### E. Guard & Invariant

Invariant:

- tên topic là constant dùng chung, không hard-code rải rác
- writer input topics là explicit, không subscribe wildcard
- topic bootstrap là step bắt buộc

Nếu xóa `WRITER_INPUT_TOPICS` và subscribe bừa mọi topic, writer sẽ dần trở thành “bể hút mọi thứ”, mất boundary rất nhanh.

#### F. Verify & Artifact

Verify topic contract bằng test:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_topic_names.py -q
```

Verify topic tồn tại sau bootstrap:

```powershell
powershell -ExecutionPolicy Bypass -File .\infra\kafka\create-topics.ps1
docker compose exec -T kafka /opt/bitnami/kafka/bin/kafka-topics.sh --bootstrap-server kafka:29092 --list
```

Artifact sau bước này:

- topic universe cố định
- bootstrap có chủ đích
- preflight về sau có cái để kiểm tra

---

### Bước 1.4. Khóa Canonical Envelope V1 Trước Khi Viết Business Event

#### A. Mục tiêu của bước này & tại sao đây là “tim” của Phase 1?

Mục tiêu là đảm bảo mọi event đi qua hệ thống đều có một lớp bao chung, có deterministic identity, có trace, có run scope, có semantic validation.

Đây là tim của Phase 1 vì toàn bộ decoupling của hệ thống phụ thuộc vào contract này.

#### B. Lý thuyết / Toán học đằng sau

Envelope v1 gồm:

```text
E =
{
event_id,
event_type,
event_version,
trace_id,
run_id,
produced_at,
source_service,
idempotency_key,
payload
}
```

Ở đây:

- `event_id` là identity của message instance
- `idempotency_key` là identity của logical event

Hai cái này tuyệt đối không được nhập nhằng.

Tư duy đúng là:

```text
event_id != idempotency_key
```

Cho run-total metrics:

```text
K_run_total
=(run_id, service_name, metric_name, labels_json)
```

chứ không phụ thuộc vào `ts`.

Labels hash được sinh theo canonical JSON:

```text
h_labels
=
SHA256(JSON_sorted(labels_json))_0:16
```

Điều này giúp:

```text
idempotency_key
=
f(event_type, run_id, logical identity)
```

ổn định qua replay.

#### C. Code Walkthrough: viết **`event-contracts.md`**, payload models, và **`envelope.py`**

Contract doc gốc là **`event-contracts.md`**.  
Nó khóa envelope fields:

```md
- event_id
- event_type
- event_version
- trace_id
- run_id
- produced_at
- source_service
- idempotency_key
- payload
```

Typed payload models nằm ở:

- **`src/event_driven_audio_analytics/shared/models/audio_metadata.py`**
- **`src/event_driven_audio_analytics/shared/models/audio_segment_ready.py`**
- **`src/event_driven_audio_analytics/shared/models/audio_features.py`**
- **`src/event_driven_audio_analytics/shared/models/system_metrics.py`**

Ví dụ **`AudioFeaturesPayload`**:

```python
@dataclass(slots=True)
class AudioFeaturesPayload:
    ts: str
    run_id: str
    track_id: int
    segment_idx: int
    artifact_uri: str
    checksum: str
    rms: float
    silent_flag: bool
    mel_bins: int
    mel_frames: int
    processing_ms: float
    manifest_uri: str | None = None
```

Trung tâm thực sự là **`src/event_driven_audio_analytics/shared/models/envelope.py`**.

Hàm **`build_idempotency_key()`**:

```python
def build_idempotency_key(
    event_type: str,
    payload: PayloadT | dict[str, object],
    event_version: str = EVENT_VERSION,
) -> str:
    payload_data = _payload_to_dict(payload)
    run_id = _require_string(payload_data, "run_id")

    if event_type == "audio.metadata":
        track_id = _require_integer(payload_data, "track_id")
        return f"{event_type}:{event_version}:{run_id}:{track_id}"

    if event_type in {"audio.segment.ready", "audio.features"}:
        track_id = _require_integer(payload_data, "track_id")
        segment_idx = _require_integer(payload_data, "segment_idx")
        return f"{event_type}:{event_version}:{run_id}:{track_id}:{segment_idx}"
```

Rule đặc biệt cho `system.metrics`:

```python
if event_type == "system.metrics":
    service_name = _require_string(payload_data, "service_name")
    metric_name = _require_string(payload_data, "metric_name")
    labels = payload_data.get("labels_json", {})
    labels_digest = _labels_digest(labels)
    if isinstance(labels, dict) and labels.get("scope") == "run_total":
        return (
            f"{event_type}:{event_version}:{run_id}:{service_name}:"
            f"{metric_name}:run_total:{labels_digest}"
        )
```

Hàm **`build_trace_id()`**:

```python
def build_trace_id(payload: PayloadT | dict[str, object], source_service: str) -> str:
    payload_data = _payload_to_dict(payload)
    run_id = _require_string(payload_data, "run_id")
    track_id = payload_data.get("track_id")
    if isinstance(track_id, int) and not isinstance(track_id, bool):
        return f"run/{run_id}/track/{track_id}"

    service_name = payload_data.get("service_name")
    if isinstance(service_name, str) and service_name:
        return f"run/{run_id}/service/{service_name}"

    return f"run/{run_id}/service/{source_service}"
```

Hàm **`build_envelope()`**:

```python
def build_envelope(
    event_type: str,
    source_service: str,
    payload: PayloadT,
    *,
    event_id: str | None = None,
    produced_at: str | None = None,
    trace_id: str | None = None,
) -> EventEnvelope[PayloadT]:
    payload_data = _payload_to_dict(payload)
    run_id = _require_string(payload_data, "run_id")
    envelope_trace_id = trace_id or build_trace_id(payload_data, source_service=source_service)

    return EventEnvelope(
        event_id=event_id or generate_event_id(),
        event_type=event_type,
        event_version=EVENT_VERSION,
        trace_id=envelope_trace_id,
        run_id=run_id,
        produced_at=produced_at or _utc_now_iso(),
        source_service=source_service,
        idempotency_key=build_idempotency_key(
            event_type=event_type,
            payload=payload_data,
            event_version=EVENT_VERSION,
        ),
        payload=payload,
    )
```

Semantic validation nằm trong **`validate_envelope_dict()`**:

```python
if payload_run_id != run_id:
    raise ValueError("Envelope run_id must match payload run_id.")

expected_idempotency_key = build_idempotency_key(
    event_type=event_type,
    payload=payload,
    event_version=EVENT_VERSION,
)
if idempotency_key != expected_idempotency_key:
    raise ValueError("Envelope idempotency_key does not match the canonical v1 identity.")
```

#### D. Why this code exists?

Từng block ở đây đều trả lời cho một bug class:

- `event_id` riêng vì cần định danh message instance
- `idempotency_key` deterministic vì replay sẽ tái phát logical event
- `trace_id` có form `run/<run_id>/...` để log correlation bền vững
- payload `run_id` phải trùng top-level `run_id` để chặn split-brain event (event tự nói nó thuộc 2 run khác nhau)

Nếu bạn hỏi “sao phải cầu kỳ thế, event JSON thôi mà”, câu trả lời là: event JSON vô kỷ luật là nguyên nhân hàng đầu của integration drift.

#### E. Guard & Invariant

Invariant:

- top-level envelope không có field lạ
- `event_version` cố định là `v1`
- `event_type` phải match topic
- payload `run_id` phải match envelope `run_id`
- `source_service` hợp lệ với `event_type`

Nếu bỏ invariant `idempotency_key` deterministic, replay sẽ trở thành roulette: cùng logical event nhưng mỗi lần replay tạo identity khác nhau, writer không còn cơ sở để hội tụ dữ liệu.

#### F. Verify & Artifact

Verify bằng unit test:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_event_models.py -q
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_event_contract_validation.py -q
```

Artifact sau bước này:

- envelope v1 canonical
- payload models typed
- deterministic idempotency rules
- semantic validator để chặn drift sớm

---

### Bước 1.5. Dựng JSON Schema, Fixtures và Contract Tests Để Khóa Tích Hợp

#### A. Mục tiêu của bước này & tại sao nó chưa phải “thừa giấy tờ”?

Mục tiêu là biến contract thành thứ máy có thể kiểm.  
Nếu chỉ có Markdown contract mà không có schema + fixture + test, contract vẫn chỉ là lời hứa.

#### B. Lý thuyết / bản chất đằng sau

Có ba lớp kiểm tra contract:

```text
Doc -> Schema -> Fixture/Test
```

Muốn contract thật sự khóa được tích hợp, bạn cần:

```text
Doc intersect Schema intersect Fixture intersect Model != empty
```

Nói bình dân: tài liệu, schema, fixture và code phải nói cùng một thứ.

#### C. Code Walkthrough: viết schema và test

Schema envelope chung ở **`schemas/envelope.v1.json`**:

```json
{
  "type": "object",
  "required": [
    "event_id",
    "event_type",
    "event_version",
    "trace_id",
    "run_id",
    "produced_at",
    "source_service",
    "idempotency_key",
    "payload"
  ],
  "additionalProperties": false
}
```

Schema topic cụ thể, ví dụ **`schemas/events/audio.metadata.v1.json`**:

```json
{
  "properties": {
    "event_type": { "const": "audio.metadata" },
    "source_service": { "const": "ingestion" },
    "payload": {
      "type": "object",
      "required": [
        "run_id",
        "track_id",
        "artist_id",
        "genre",
        "source_audio_uri",
        "validation_status",
        "duration_s"
      ],
      "additionalProperties": false
    }
  }
}
```

Fixtures canonical nằm dưới **`tests/fixtures/events/v1/`**.  
Ví dụ **`audio.features.valid.json`**:

```json
{
  "event_id": "evt-features-v1-001",
  "event_type": "audio.features",
  "event_version": "v1",
  "trace_id": "run/demo-run/track/2",
  "run_id": "demo-run",
  "produced_at": "2026-04-02T00:00:10Z",
  "source_service": "processing",
  "idempotency_key": "audio.features:v1:demo-run:2:0",
  "payload": {
    "ts": "2026-04-02T00:00:10Z",
    "run_id": "demo-run",
    "track_id": 2,
    "segment_idx": 0,
    "artifact_uri": "/artifacts/runs/demo-run/segments/2/0.wav",
    "checksum": "sha256:segment-000",
    "rms": 0.42,
    "silent_flag": false,
    "mel_bins": 128,
    "mel_frames": 300,
    "processing_ms": 12.5
  }
}
```

Test contract fixture shape trong **`tests/integration/test_contract_fixtures.py`**:

```python
def test_audio_features_fixture_matches_schema_shape(self) -> None:
    self.assert_fixture_matches_required_fields("audio.features.v1.json", "audio.features.valid.json")
```

Test semantic validation trong **`tests/unit/test_event_contract_validation.py`**:

```python
def test_run_id_mismatch_fails_semantic_validation(self) -> None:
    validator = load_validator("audio.metadata.v1.json")
    envelope = load_json(FIXTURES_DIR / "audio.metadata.run-id-mismatch.json")

    validator.validate(envelope)

    with self.assertRaisesRegex(ValueError, "run_id"):
        validate_envelope_dict(envelope, expected_event_type="audio.metadata")
```

#### D. Why this code exists?

Schema và fixtures tồn tại để chống một lỗi rất phổ biến: “code producer và code consumer cùng đổi sai một kiểu nên local test vẫn xanh”.

Khi có fixture canonical:

- producer có một target thật để build theo
- consumer có một input thật để parse theo
- reviewer có một artifact ổn định để đọc

#### E. Guard & Invariant

Invariant:

- `additionalProperties: false` ở schema
- fixture valid phải đủ required fields
- fixture invalid phải khóa các failure mode quan trọng như version mismatch, run_id mismatch, payload type mismatch

Nếu bỏ `additionalProperties: false`, contract drift sẽ len lỏi bằng “thêm field tạm”.

#### F. Verify & Artifact

Verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\integration\test_contract_fixtures.py -q
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_event_contract_validation.py -q
```

Artifact sau bước này:

- schemas machine-checkable
- fixtures canonical
- contract drift có detector tự động

---

### Bước 1.6. Dựng Timescale Schema Và Dashboard SQL Surface Ngay Từ Đầu

#### A. Mục tiêu của bước này & tại sao DB phải xuất hiện sớm như vậy?

Vì observability trong repo này không phải phụ kiện. Nó là một phần của claim project.  
Nếu DB schema và dashboard SQL surface không được dựng sớm, các phase sau rất dễ publish event xong rồi… không biết persist gì, query gì, demo gì.

#### B. Lý thuyết / Toán học đằng sau

Repo này chọn hướng:

```text
Kafka -> Writer -> TimescaleDB -> Grafana
```

chứ không phải:

```text
Kafka -> Grafana trực tiếp
```

Lý do: dashboard ở đây phải phản ánh **persisted truth** (sự thật đã được ghi bền vững), không chỉ phản ánh “message vừa bay qua broker”.

Với feature rows, identity mong muốn là:

```text
K_feature^logical = (run_id, track_id, segment_idx)
```

Nhưng Timescale hypertable đang cần primary key vật lý chứa cột thời gian:

```text
K_feature^physical = (ts, run_id, track_id, segment_idx)
```

Đây là một **Conflict** có chủ đích, và Phase 1 phải ghi nhận nó từ đầu.

#### C. Code Walkthrough: viết SQL init

Extension file **`infra/sql/001_extensions.sql`** rất ngắn:

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
```

Core tables trong **`infra/sql/002_core_tables.sql`**:

```sql
CREATE TABLE IF NOT EXISTS track_metadata (
    run_id TEXT NOT NULL,
    track_id BIGINT NOT NULL,
    artist_id BIGINT NOT NULL,
    genre TEXT NOT NULL,
    subset TEXT NOT NULL DEFAULT 'small',
    source_audio_uri TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    duration_s DOUBLE PRECISION NOT NULL,
    manifest_uri TEXT,
    checksum TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, track_id)
);
```

```sql
CREATE TABLE IF NOT EXISTS audio_features (
    ts TIMESTAMPTZ NOT NULL,
    run_id TEXT NOT NULL,
    track_id BIGINT NOT NULL,
    segment_idx INTEGER NOT NULL,
    artifact_uri TEXT NOT NULL,
    checksum TEXT NOT NULL,
    manifest_uri TEXT,
    rms DOUBLE PRECISION NOT NULL,
    silent_flag BOOLEAN NOT NULL,
    mel_bins INTEGER NOT NULL,
    mel_frames INTEGER NOT NULL,
    processing_ms DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ts, run_id, track_id, segment_idx)
);

SELECT create_hypertable('audio_features', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_audio_features_lookup
ON audio_features (run_id, track_id, segment_idx);
```

```sql
CREATE TABLE IF NOT EXISTS system_metrics (
    ts TIMESTAMPTZ NOT NULL,
    run_id TEXT NOT NULL,
    service_name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL,
    labels_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    unit TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

```sql
CREATE TABLE IF NOT EXISTS run_checkpoints (
    consumer_group TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    partition_id INTEGER NOT NULL,
    run_id TEXT NOT NULL,
    last_committed_offset BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_group, topic_name, partition_id)
);
```

Operational views trong **`infra/sql/003_operational_views.sql`**:

```sql
CREATE OR REPLACE VIEW vw_dashboard_metric_events AS
SELECT
    ts,
    run_id,
    service_name,
    metric_name,
    metric_value,
    COALESCE(labels_json ->> 'scope', 'event') AS metric_scope,
    COALESCE(
        labels_json ->> 'status',
        CASE
            WHEN metric_name IN ('feature_errors', 'write_failures') THEN 'error'
            ELSE 'ok'
        END
    ) AS metric_status,
    labels_json ->> 'topic' AS topic_name,
    labels_json ->> 'failure_class' AS failure_class,
    unit,
    labels_json
FROM system_metrics;
```

#### D. Why this code exists?

Mỗi bảng ở đây giải quyết một loại áp lực:

- `track_metadata`: dimension table cho outcome của track, kể cả reject
- `audio_features`: segment summary time-series
- `system_metrics`: observability surface chung
- `run_checkpoints`: persistence-side memory cho consumer progress
- `welford_snapshots`: future path được khai báo sớm, dù runtime chưa persist

View **`vw_dashboard_metric_events`** tồn tại để tránh lặp business logic JSONB ở Grafana query.  
Nếu dashboard query raw `labels_json` khắp nơi, bạn sẽ có 5 panel, 5 chỗ parse JSON, 5 nơi drift.

#### E. Guard & Invariant

Invariant:

- schema phải đi từ file SQL init, không click DB bằng tay
- `track_metadata` natural key là `(run_id, track_id)`
- checkpoint primary key là `(consumer_group, topic_name, partition_id)`
- logical identity của feature row phải được document rõ ngay cả khi physical PK chứa `ts`

Một guard tương đối “đi trước một bước” là helper advisory lock trong **`src/event_driven_audio_analytics/shared/db.py`**:

```python
def advisory_lock_key(*parts: object) -> int:
    digest = hashlib.blake2b(
        "::".join(str(part) for part in parts).encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)

def acquire_transaction_advisory_lock(cursor: Cursor, *parts: object) -> None:
    cursor.execute("SELECT pg_advisory_xact_lock(%s);", (advisory_lock_key(*parts),))
```

`advisory lock` (khóa logic do PostgreSQL cấp theo một key do mình tự tính, không cần phải là một row cụ thể) được đặt sẵn vì Phase 4 sẽ cần bảo vệ natural-key semantics trên hypertable, nơi `ON CONFLICT` đơn thuần không kể hết câu chuyện logic.

#### F. Verify & Artifact

Verify schema contract:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\integration\test_writer_schema_contract.py -q
```

Verify tables tồn tại sau bootstrap:

```powershell
docker compose exec -T timescaledb psql -U audio_analytics -d audio_analytics -c "\dt"
docker compose exec -T timescaledb psql -U audio_analytics -d audio_analytics -c "\dv"
```

Artifact sau bước này:

- DB có landing zone thật cho writer
- dashboard có SQL surface thật để bám
- conflict logical-key vs physical-key đã được document chứ không bị chôn

---

### Bước 1.7. Dựng Shared Runtime Helpers: Settings, Kafka IO, Storage, Logging, Preflight

#### A. Mục tiêu của bước này & tại sao bước này nối giữa “contract” và “runtime”?

Mục tiêu là làm cho mỗi service boot với cùng một ngôn ngữ runtime:

- cùng cách đọc env
- cùng cách serialize/deserialize envelope
- cùng path convention cho claim-check
- cùng logging shape
- cùng preflight philosophy

Nếu không có lớp shared này, mỗi service sẽ tự phát minh runtime dialect riêng.

#### B. Lý thuyết / bản chất đằng sau

Shared runtime helpers chính là “grammar” của toàn repo.  
Không phải business logic, nhưng là lớp làm cho business logic ghép được với nhau.

Về Kafka producer:

```text
delivery safety ~ idempotence + acks=all + delivery confirmation
```

Về checkpoint-aware consumer:

```text
commit correctness = disable auto commit + commit after successful sink
```

Về claim-check path:

```text
artifact root = /artifacts/runs/<run_id>/...
```

#### C. Code Walkthrough: đọc các helper quan trọng

**`src/event_driven_audio_analytics/shared/settings.py`**:

```python
@dataclass(slots=True)
class BaseServiceSettings:
    service_name: str
    run_id: str
    kafka_bootstrap_servers: str
    artifacts_root: Path

def load_base_service_settings(service_name: str) -> BaseServiceSettings:
    return BaseServiceSettings(
        service_name=os.getenv("SERVICE_NAME", service_name),
        run_id=os.getenv("RUN_ID", "demo-run"),
        kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092"),
        artifacts_root=Path(os.getenv("ARTIFACTS_ROOT", "/app/artifacts")),
    )
```

**`src/event_driven_audio_analytics/shared/storage.py`**:

```python
def run_root(artifacts_root: Path, run_id: str) -> Path:
    return artifacts_root / "runs" / run_id

def segment_artifact_uri(artifacts_root: Path, run_id: str, track_id: int, segment_idx: int) -> str:
    return (run_root(artifacts_root, run_id) / "segments" / str(track_id) / f"{segment_idx}.wav").as_posix()

def manifest_uri(artifacts_root: Path, run_id: str) -> str:
    return (run_root(artifacts_root, run_id) / "manifests" / "segments.parquet").as_posix()
```

**`src/event_driven_audio_analytics/shared/kafka.py`** producer config:

```python
def producer_config(...):
    return {
        "bootstrap.servers": bootstrap_servers,
        "client.id": client_id,
        "enable.idempotence": True,
        "acks": "all",
        "retries": retries,
        "retry.backoff.ms": retry_backoff_ms,
        "retry.backoff.max.ms": retry_backoff_max_ms,
        "delivery.timeout.ms": delivery_timeout_ms,
    }
```

Consumer config:

```python
def consumer_config(...):
    config = {
        "bootstrap.servers": bootstrap_servers,
        "group.id": group_id,
        "client.id": client_id,
        "auto.offset.reset": auto_offset_reset,
        "enable.auto.commit": enable_auto_commit,
        "enable.auto.offset.store": enable_auto_offset_store,
    }
```

Delivery confirmation helper:

```python
def produce_and_wait(...):
    delivery_state = {"delivered": False, "error": None}
    ...
    while not bool(delivery_state["delivered"]):
        remaining_s = deadline - monotonic()
        if remaining_s <= 0:
            break
        remaining_messages = flush(min(remaining_s, 0.5))
    ...
    if delivery_error is not None:
        raise KafkaDeliveryError(...)
```

Structured logging trong **`src/event_driven_audio_analytics/shared/logging.py`**:

```python
payload = {
    "ts": ...,
    "level": record.levelname,
    "service": getattr(record, "service_name", record.name),
    "logger": record.name,
    "message": record.getMessage(),
}
```

Và **`ServiceLoggerAdapter.bind()`**:

```python
def bind(self, **context: object) -> "ServiceLoggerAdapter":
    merged = dict(self.extra)
    for key, value in context.items():
        if key == "service_name":
            merged[key] = value
        elif _should_include_log_value(key, value):
            merged[key] = value
        else:
            merged.pop(key, None)
    return ServiceLoggerAdapter(self.logger, merged)
```

Preflight writer trong **`src/event_driven_audio_analytics/writer/modules/runtime.py`**:

```python
REQUIRED_WRITER_TOPICS = (
    AUDIO_METADATA,
    AUDIO_FEATURES,
    SYSTEM_METRICS,
)

REQUIRED_WRITER_TABLES = (
    "track_metadata",
    "audio_features",
    "system_metrics",
    "run_checkpoints",
)
```

Preflight ingestion trong **`src/event_driven_audio_analytics/ingestion/modules/runtime.py`** có write probe:

```python
def _probe_directory_write(path: Path, *, label: str) -> None:
    probe_path = path / f".ingestion-write-probe-{uuid4().hex}"
    probe_path.write_bytes(b"")
    probe_path.unlink()
```

#### D. Why this code exists?

Đây là một cụm code rất “khó được khen” nhưng cực kỳ quan trọng:

- `load_base_service_settings()` tồn tại để mọi service nói cùng tiếng env
- `storage.py` tồn tại để path claim-check không drift từng module
- `produce_and_wait()` tồn tại vì publish không được tính là xong khi chỉ gọi `produce()`
- JSON logging tồn tại để log có thể machine-parse và correlate theo `run_id`, `trace_id`
- preflight tồn tại để fail sớm, đúng dependency, đúng nguyên nhân

Một chi tiết đáng học là write probe ở artifact root. Kiểm `os.access()` thôi chưa đủ; mount permission trên container có thể nhìn như writable nhưng fail lúc ghi thật. Probe file ngắn là cách kiểm thực dụng hơn nhiều.

#### E. Guard & Invariant

Invariant:

- mọi service dùng cùng `RUN_ID`
- claim-check path shape luôn là `/artifacts/runs/<run_id>/...`
- Kafka producer phải chờ delivery report
- consumer auto-commit mặc định phải tắt
- preflight là gate chính thức, không phải “nice to have”

Nếu bỏ `produce_and_wait()`, bạn sẽ có false confidence: code nghĩ event đã gửi, nhưng broker chưa hề ack.

#### F. Verify & Artifact

Verify runtime preflight:

```powershell
docker compose run --rm --no-deps ingestion preflight
docker compose run --rm --no-deps processing preflight
docker compose run --rm --no-deps writer preflight
```

Verify unit tests cho runtime:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_writer_runtime.py -q
```

Artifact sau bước này:

- shared runtime grammar thống nhất
- fail-fast startup path sẵn sàng
- service boot logic bắt đầu có thể kiểm được

---

### Bước 1.8. Dựng Fake-Event Writer Smoke Path Để Chứng Minh Spine Thật Sự Khép Kín

#### A. Mục tiêu của bước này & tại sao nó là điểm kết của CHUNK 1?

Mục tiêu là chứng minh rằng trước cả khi ingestion thật và processing thật hoàn chỉnh, ta đã có thể:

- dựng Kafka topics
- phát canonical events
- cho writer consume/persist/checkpoint
- kiểm DB state
- kiểm idempotent replay ở mức đầu tiên

Đây là điểm kết của CHUNK 1 vì nó là bằng chứng rằng spine không chỉ “trông hợp lý trên giấy”, mà đã có một đường tích hợp chạy được.

#### B. Lý thuyết / Toán học đằng sau

Fake-event smoke path là vertical slice nhỏ nhất của integration.

Nó kiểm ý tưởng:

```text
Canonical Event -> Kafka -> Writer -> DB
```

Với idempotent sink, nếu replay cùng logical feature event:

```text
F(F(S, e), e) = F(S, e)
```

Nghĩa là replay không được nhân đôi logical state.

Với run-total metric snapshot:

```text
latest snapshot => 1 logical row
```

dù trước đó đã seed duplicate rows vật lý ở nhiều hypertable chunks.

#### C. Code Walkthrough: smoke publisher, writer pipeline, smoke script

Fake publisher trong **`src/event_driven_audio_analytics/smoke/publish_fake_events.py`**:

```python
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "events" / "v1"

def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
```

Publish path:

```python
if args.only_run_total_metric:
    fixture_by_topic = (
        (SYSTEM_METRICS, load_fixture("system.metrics.run_total.valid.json")),
    )
else:
    fixture_by_topic = (
        (AUDIO_METADATA, load_fixture("audio.metadata.valid.json")),
        (AUDIO_FEATURES, load_fixture("audio.features.valid.json")),
    )

for topic, envelope in fixture_by_topic:
    producer.produce(topic=topic, value=serialize_envelope(envelope))
```

Writer app entrypoint **`src/event_driven_audio_analytics/writer/app.py`**:

```python
if args.command == "preflight":
    check_runtime_dependencies(settings)
    return

pipeline = WriterPipeline(settings=settings)
pipeline.run(logger=logger)
```

Writer pipeline **`src/event_driven_audio_analytics/writer/pipeline.py`**:

```python
raw_envelope = deserialize_envelope(record.value)
context = self._extract_record_context(raw_envelope)
outcome = self._persist_record(...)
consumer.commit(message=record.message, asynchronous=False)
```

Thứ tự persistence rất quan trọng:

```python
rows_written = persist_envelope_payload(...)
checkpoint_record = build_checkpoint_record(...)
checkpoint_rows = persist_checkpoint(cursor, checkpoint_record)
decision = build_commit_decision(
    rows_written=rows_written,
    checkpoints_ready=checkpoint_rows > 0,
)
if not decision.commit_allowed:
    raise WriterStageError(...)
```

Sau đó writer ghi metric nội bộ trực tiếp vào DB:

```python
persist_system_metrics(
    cursor,
    build_writer_metric_payload(
        run_id=run_id,
        topic=record.topic,
        metric_name="write_ms",
        metric_value=write_elapsed_ms,
        unit="ms",
        status="ok",
        partition=record.partition,
        offset=record.offset,
    ),
)
```

Smoke script **`scripts/smoke/check-writer-flow.ps1`** ghép tất cả lại:

```powershell
docker compose down --remove-orphans
docker compose up --build -d kafka timescaledb
& (Resolve-Path "infra/kafka/create-topics.ps1")
docker compose build writer
docker compose run --rm --no-deps writer preflight
docker compose up -d --no-deps writer
docker compose run --rm --entrypoint python writer -m event_driven_audio_analytics.smoke.publish_fake_events
```

Script còn replay lại fake event để kiểm idempotency:

```powershell
docker compose run --rm --entrypoint python writer -m event_driven_audio_analytics.smoke.publish_fake_events
Wait-ForQuery "SELECT COUNT(*) FROM audio_features WHERE run_id = 'demo-run' AND track_id = 2 AND segment_idx = 0;" "1"
```

Và seed duplicate run_total metric rows để kiểm snapshot rewrite:

```powershell
Invoke-Sql "INSERT INTO system_metrics (...) VALUES ('2024-01-01T00:00:00Z', 'demo-run', 'ingestion', 'tracks_total', 1.0, jsonb_build_object('scope', 'run_total'), 'count');"
Invoke-Sql "INSERT INTO system_metrics (...) VALUES ('2025-02-01T00:00:00Z', 'demo-run', 'ingestion', 'tracks_total', 2.0, jsonb_build_object('scope', 'run_total'), 'count');"
docker compose run --rm --entrypoint python writer -m event_driven_audio_analytics.smoke.publish_fake_events --only-run-total-metric
```

#### D. Why this code exists?

Smoke path này tồn tại để giải quyết một sự thật kỹ thuật khó chịu:  
“có schema” không có nghĩa “dịch vụ ghép được với nhau”.

Publisher fake event giúp:

- test contract bằng dữ liệu canonical
- không cần chờ ingestion/processing đầy đủ mới kiểm writer
- phát hiện sớm drift giữa fixtures, envelope parser, DB persistence và checkpoint logic

Seed duplicate run_total metrics là một đòn kiểm rất senior: nó mô phỏng chính xác loại rác dữ liệu replay có thể tạo ra trên hypertable.

#### E. Guard & Invariant

Invariant:

- writer chỉ commit offset sau khi persist payload + checkpoint thành công
- replay cùng fake feature event không được tạo thêm logical feature row
- system metric `run_total` phải hội tụ về 1 logical snapshot row
- `audio.dlq` mới reserved; failure path hiện tại phải dừng record uncommitted để inspect

Nếu bạn commit offset trước persistence, smoke path này sẽ không còn là smoke path cho correctness mà chỉ là smoke path cho “đã poll được Kafka”.

#### F. Verify & Artifact

Chạy đúng smoke chính thức:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-writer-flow.ps1
```

Hoặc Linux:

```sh
bash ./scripts/smoke/check-writer-flow.sh
```

Verify test logic quanh writer:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_writer_pipeline.py -q
```

Artifact sau bước này:

- Kafka topics đã bootstrap
- writer preflight pass
- fake `audio.metadata` và `audio.features` được persist vào `track_metadata` và `audio_features`
- `run_checkpoints` có row cho topic đã consume
- replay cùng fake event vẫn giữ `audio_features` logical row count bằng `1`
- run-total metric duplicate repair hoạt động trên Timescale path hiện tại

---

## Kết Thúc CHUNK 1: Sau Phase 0 Và Phase 1, Bạn Phải Có Gì Trong Tay?

Nếu làm đúng CHUNK 1, trước khi chạm vào ingestion/processing business logic thật, bạn đã có:

1. Một bộ ground-truth docs khóa mission, scope, ownership, audio semantics và build order.
2. Một Python package có dependency slicing sạch theo vai trò service.
3. Một Docker Compose spine gồm Kafka KRaft, TimescaleDB, Grafana và ba service app.
4. Một topic universe rõ ràng, bootstrap có chủ đích, auto-create topic bị tắt.
5. Một canonical event envelope v1 với deterministic `idempotency_key`, `trace_id`, `run_id`.
6. Một bộ JSON schema + fixtures + tests để chặn contract drift.
7. Một Timescale schema + dashboard SQL surface đủ để làm persistence và observability backbone.
8. Một shared runtime grammar cho env, logging, claim-check paths, Kafka IO, preflight.
9. Một fake-event writer smoke path chứng minh bộ xương tích hợp đã chạy được.

Nếu thiếu một trong chín thứ trên, đừng bước sang CHUNK 2.  
Lý do rất đơn giản: CHUNK 2 sẽ bắt đầu viết ingestion pipeline thật, và ingestion thật mà đặt lên một spine lỏng là tự đẩy mình vào debugging đa chiều:

- không biết lỗi do audio hay do contract
- không biết lỗi do Kafka hay do DB
- không biết lỗi do payload hay do checkpoint

CHUNK 1 sinh ra để chặn chính loại hỗn loạn đó.

## Những Lệnh Verify Nên Thuộc Lòng Sau CHUNK 1

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-compose.ps1
powershell -ExecutionPolicy Bypass -File .\run-demo.ps1
powershell -ExecutionPolicy Bypass -File .\infra\kafka\create-topics.ps1
docker compose run --rm --no-deps writer preflight
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-writer-flow.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_event_models.py -q
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_event_contract_validation.py -q
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\integration\test_writer_schema_contract.py -q
```

## Dấu Hiệu Bạn Đang Đi Đúng Trước Khi Sang CHUNK 2

- Bạn giải thích được vì sao `event_id` và `idempotency_key` là hai thứ khác nhau.
- Bạn giải thích được vì sao Kafka auto-create topic bị tắt.
- Bạn giải thích được vì sao DB schema và dashboard views phải có từ sớm, dù ingestion thật chưa xong.
- Bạn giải thích được vì sao fake-event smoke path là bắt buộc, không phải “test cho có”.
- Bạn giải thích được vì sao replay safety phải được nghĩ từ CHUNK 1.

Đến đây kết thúc CHUNK 1.

# CHUNK 2

## Phase 2. Xây Dựng Ingestion Pipeline

### Bước 2.1. Mở `src/event_driven_audio_analytics/ingestion/modules/metadata_loader.py` và khóa metadata population trước khi đụng vào DSP

Gõ `MetadataRecord` trước. Sau đó gõ theo đúng thứ tự `_build_flattened_headers -> _load_fma_metadata_frame -> _select_required_columns -> load_small_subset_metadata`.  
Đừng nhảy cóc sang `decode_audio_pyav()` khi còn chưa biết chính xác track nào được phép đi vào pipeline.

`tracks.csv` của FMA không phải loại CSV một dòng header là xong. Nó có ba dòng đầu mang ý nghĩa schema. Cách đúng ở đây là parse kiểu “sandwich”:

```text
CSV body = read_csv(skip_rows=3)
```

nhưng:

```text
header logic = f(row_0,row_1)
```

Rồi mới ghép hai nửa đó lại:

```text
frame_named = rename(frame_raw, flattened_headers)
```

Dòng code chứng minh trực tiếp ý tưởng này:

```python
def _build_flattened_headers(csv_path: Path) -> list[str]:
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        row0 = next(reader)
        row1 = next(reader)

    filled_categories: list[str] = []
    current_category = ""
    for raw_category in row0:
        stripped = raw_category.strip()
        if stripped:
            current_category = stripped
        filled_categories.append(current_category)

    headers: list[str] = []
    for index, (raw_category, raw_attribute) in enumerate(zip(filled_categories, row1, strict=True)):
        category = raw_category.strip()
        attribute = raw_attribute.strip()
        if index == 0:
            headers.append("track_id")
        elif category and attribute:
            headers.append(f"{category}.{attribute}")
        elif attribute:
            headers.append(attribute)
        else:
            headers.append(f"_unnamed_{index}")

    return headers


def _load_fma_metadata_frame(csv_path: Path) -> pl.DataFrame:
    flattened_headers = _build_flattened_headers(csv_path)
    frame = pl.read_csv(
        csv_path,
        skip_rows=3,
        has_header=False,
        infer_schema_length=0,
        null_values=[""],
    )
    if len(frame.columns) != len(flattened_headers):
        raise ValueError(
            "FMA tracks.csv column count did not match flattened-header parsing."
        )
    return frame.rename(dict(zip(frame.columns, flattened_headers, strict=True)))
```

Block core tiếp theo không phải là “build label map”, mà là **khóa population**.  
Ta chọn đúng các cột cần thiết, rồi cắt `subset=small`, rồi loại `genre_label` rỗng, rồi mới sort và giới hạn. Trật tự đó không phải thẩm mỹ; nó là bug-prevention.

```text
R_small
=
{r in R | subset(r)=small and genre(r) != empty}
```

Gõ block này ngay sau parser:

```python
def _select_required_columns(frame: pl.DataFrame, subset: str) -> pl.DataFrame:
    column_by_key: dict[str, str | None] = {
        "track_id": "track_id",
        "artist_id": None,
        "genre_top": None,
        "subset": None,
        "duration": None,
    }

    for column_name in frame.columns:
        lowered = column_name.lower()
        if lowered == "artist.id":
            column_by_key["artist_id"] = column_name
        elif lowered == "set.subset":
            column_by_key["subset"] = column_name
        elif lowered == "track.duration":
            column_by_key["duration"] = column_name
        elif "genre_top" in lowered:
            column_by_key["genre_top"] = column_name

    missing = [key for key, value in column_by_key.items() if value is None]
    if missing:
        raise KeyError(f"tracks.csv is missing required FMA columns: {', '.join(sorted(missing))}.")

    return (
        frame.select(
            [
                pl.col("track_id").cast(pl.Int64).alias("track_id"),
                pl.col(str(column_by_key["artist_id"])).cast(pl.Int64).alias("artist_id"),
                pl.col(str(column_by_key["genre_top"])).str.strip_chars().alias("genre_label"),
                pl.col(str(column_by_key["subset"])).str.strip_chars().alias("subset"),
                pl.col(str(column_by_key["duration"]))
                .cast(pl.Float64, strict=False)
                .alias("declared_duration_s"),
            ]
        )
        .filter(pl.col("subset") == subset)
        .filter(pl.col("genre_label").is_not_null() & (pl.col("genre_label") != ""))
        .sort("track_id")
    )
```

Tại sao phải filter `subset=small` trước khi build bất kỳ label universe nào?  
Vì label map đúng bản chất phải được xây trên **population sẽ replay**, không phải trên toàn thế giới metadata. Nếu bạn làm ngược:

```python
raw = _load_fma_metadata_frame(csv_path)
label_map = {name: idx for idx, name in enumerate(raw["track.genre_top"].unique())}
small = raw.filter(pl.col("set.subset") == "small")
```

thì `label_map` không còn đại diện cho PoC `small` nữa. Cả đội từng gọi loại trôi này là bug “16K genres”: không phải tự nhiên có 16K genre thật, mà là universe nhãn bị phình theo full CSV trước khi cắt population, kéo theo mapping và memory footprint sai ngữ nghĩa ngay từ cửa vào.

Gõ hàm public cuối cùng như sau, và giữ nguyên thứ tự `allowlist -> max_tracks -> duration guard -> build record`:

```python
def load_small_subset_metadata(
    metadata_csv_path: str,
    *,
    audio_root_path: str,
    subset: str = "small",
    track_id_allowlist: tuple[int, ...] = (),
    max_tracks: int | None = None,
) -> list[MetadataRecord]:
    if not metadata_csv_path:
        raise ValueError("metadata_csv_path must not be empty")
    if not audio_root_path:
        raise ValueError("audio_root_path must not be empty")

    csv_path = Path(metadata_csv_path)
    frame = _select_required_columns(_load_fma_metadata_frame(csv_path), subset=subset)

    if track_id_allowlist:
        frame = frame.filter(pl.col("track_id").is_in(track_id_allowlist))

    if max_tracks is not None:
        frame = frame.head(max_tracks)

    invalid_duration_frame = frame.filter(
        pl.col("declared_duration_s").is_null() | (pl.col("declared_duration_s") <= 0.0)
    )
    if invalid_duration_frame.height:
        invalid_track_ids = invalid_duration_frame["track_id"].head(5).to_list()
        raise ValueError(
            "tracks.csv must provide positive track.duration values for the selected subset. "
            f"Invalid track_ids include: {invalid_track_ids}."
        )

    audio_root = Path(audio_root_path)
    records: list[MetadataRecord] = []
    for row in frame.iter_rows(named=True):
        track_id = int(row["track_id"])
        source_path = resolve_audio_path(track_id)
        records.append(
            MetadataRecord(
                track_id=track_id,
                artist_id=int(row["artist_id"]),
                genre_label=str(row["genre_label"]),
                subset=str(row["subset"]),
                source_path=source_path,
                source_audio_uri=(audio_root / source_path).as_posix(),
                declared_duration_s=float(row["declared_duration_s"]),
            )
        )
    return records
```

Hai guard rất đáng tiền nằm ở đây:

- `declared_duration_s` phải dương ngay từ metadata phase, vì reject path sau này vẫn cần `duration_s` hợp lệ để bắn `audio.metadata` schema-valid dù track chết ở `missing_file` hay `probe_failed`.
- `resolve_audio_path()` phải zero-pad `track_id` thành `000/000002.mp3`, không được “tự tiện” dùng tên file gốc từ CSV, vì layout FMA trên disk là deterministic theo `track_id`.

Vết sẹo buộc phải viết block này: parse header non-deterministic và build label map trên sai population. Khi đó lỗi không nổ ở `metadata_loader.py`; nó nổ muộn hơn ở validation, ở analytics, hoặc tệ nhất là ở lúc demo khi cùng một `track_id` lại trỏ tới một universe genre không còn khớp với subset đang chạy.

Gõ xong bước này, đừng chạy full pipeline vội. Chạy đúng unit test đang khóa semantics:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_ingestion_pipeline.py -q -k "metadata_etl"
```

Nếu muốn test đúng chỗ duration guard:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_ingestion_pipeline.py -q -k "requires_positive_track_duration"
```

Artifact bạn cần thấy trong đầu sau bước này không phải event. Nó là một danh sách `MetadataRecord` đã được population-lock, có `track_id`, `artist_id`, `genre_label`, `subset`, `source_audio_uri`, `declared_duration_s`.

---

### Bước 2.2. Mở `src/event_driven_audio_analytics/shared/audio.py` rồi `audio_validator.py`; gõ validation path theo đúng thứ tự chết người

Ở bước này, đừng gõ `validate_audio_record()` trước.  
Mở `shared/audio.py` trước, vì validator chỉ đúng khi decode/probe semantics đã đúng.

Block đầu tiên cần sống là `AudioProbe`, `DecodedAudio`, rồi `probe_audio()`. Mục tiêu là tách **cheap probe** khỏi **expensive decode**:

```text
probe(x) << decode(x)
```

và validator sẽ dùng probe để quyết định sớm:

```text
status(r) =
- missing_file, not exists(path)
- probe_failed, probe(path) fails
- too_short, duration(path) < 1.0
- decode_failed, decode(path) fails
- silent, RMS_dBFS(decode(path)) < -60
- validated, otherwise
```

Gõ `probe_audio()` trước:

```python
@dataclass(slots=True)
class AudioProbe:
    duration_s: float
    sample_rate_hz: int


def probe_audio(path: str | Path) -> AudioProbe:
    container = _open_audio(path)
    try:
        stream = container.streams.audio[0]
        if stream.rate is None:
            raise RuntimeError(f"Audio sample rate is unavailable for {path}.")

        duration_s: float | None = None
        if stream.duration is not None and stream.time_base is not None:
            duration_s = float(stream.duration * stream.time_base)
        elif container.duration is not None:
            duration_s = float(container.duration / av.time_base)

        if duration_s is None:
            raise RuntimeError(f"Audio duration is unavailable for {path}.")

        return AudioProbe(duration_s=duration_s, sample_rate_hz=int(stream.rate))
    finally:
        container.close()
```

Sau đó gõ `decode_audio_pyav()`. Đây là chỗ math phải dính vào code, không nói chung chung được.  
Ta cần mono 32 kHz đúng theo legacy semantics:

```text
x_mono[n] = (1 / C)sum_c=1^C x_c[n]
```

```text
f_s^target = 32000
```

Code phải chứng minh đúng hai ý đó:

```python
@dataclass(slots=True)
class DecodedAudio:
    waveform: np.ndarray
    sample_rate_hz: int
    duration_s: float
    original_sample_rate_hz: int


def decode_audio_pyav(path: str | Path, *, target_sample_rate_hz: int) -> DecodedAudio:
    container = _open_audio(path)
    try:
        stream = container.streams.audio[0]
        if stream.rate is None:
            raise RuntimeError(f"Audio sample rate is unavailable for {path}.")

        original_sample_rate_hz = int(stream.rate)
        resampler: av.audio.resampler.AudioResampler | None = None
        frames: list[np.ndarray] = []
        for frame in container.decode(audio=0):
            if resampler is None:
                layout_name = frame.layout.name if frame.layout is not None else "mono"
                resampler = av.audio.resampler.AudioResampler(
                    format="fltp",
                    layout=layout_name,
                    rate=target_sample_rate_hz,
                )
            for output_frame in resampler.resample(frame):
                frames.append(output_frame.to_ndarray().astype(np.float32, copy=False))

        if resampler is not None:
            for output_frame in resampler.resample(None):
                frames.append(output_frame.to_ndarray().astype(np.float32, copy=False))

        if not frames:
            raise RuntimeError(f"No audio frames decoded from {path}.")

        waveform = np.concatenate(frames, axis=1)
        if waveform.ndim == 1:
            waveform = waveform[np.newaxis, :]
        elif waveform.shape[0] > 1:
            waveform = waveform.mean(axis=0, keepdims=True, dtype=np.float32)

        duration_s = waveform.shape[-1] / float(target_sample_rate_hz)
        return DecodedAudio(
            waveform=waveform,
            sample_rate_hz=target_sample_rate_hz,
            duration_s=duration_s,
            original_sample_rate_hz=original_sample_rate_hz,
        )
    finally:
        container.close()
```

Tại sao resampler giữ `layout=layout_name` thay vì ép ngay `mono`?  
Vì đây là vết sẹo có thật. Một bản cũ để FFmpeg downmix ngay trong lúc resample, và amplitude ra lệch khoảng `sqrt(2)` so với legacy path vốn **resample theo layout gốc rồi mới arithmetic-mean fold-down**.

Math ngắn gọn:

```text
auto-downmix != (L + R / 2)
```

Code hiện tại tránh drift đó bằng hai ranh giới ownership:

- `output_frame.to_ndarray()` chốt dữ liệu PyAV ra NumPy.
- `np.concatenate(frames, axis=1)` chốt một buffer waveform liền mạch, owned bởi pipeline hiện tại.

Rồi mới tới `compute_rms_db()`:

```text
RMS(x)=sqrt((1 / N)sum_n=1^Nx_n^2)
```

```text
RMS_dBFS(x)=20log_10(RMS(x))
```

Code:

```python
def compute_rms_db(waveform: np.ndarray) -> float:
    if waveform.size == 0:
        return -math.inf

    mono_waveform = waveform.astype(np.float32, copy=False)
    rms = float(np.sqrt(np.mean(np.square(mono_waveform), dtype=np.float64)))
    if rms < 1e-10:
        return -math.inf

    return 20.0 * math.log10(rms)
```

Chỉ khi `shared/audio.py` đã ổn, mới mở `src/event_driven_audio_analytics/ingestion/modules/audio_validator.py` và gõ validator.  
Trình tự gõ chuẩn là `exists` guard trước, rồi mới hash:

```python
def validate_audio_record(
    record: MetadataRecord,
    *,
    target_sample_rate_hz: int,
    min_duration_s: float = 1.0,
    silence_threshold_db: float = -60.0,
) -> ValidationResult:
    file_path = Path(record.source_audio_uri)
    if not file_path.exists():
        return ValidationResult(
            record=record,
            validation_status=VALIDATION_STATUS_MISSING_FILE,
            validation_error=f"Audio file does not exist: {file_path.as_posix()}",
        )

    checksum = sha256_file(file_path)

    try:
        probe = probe_audio(file_path)
    except Exception as exc:
        return ValidationResult(
            record=record,
            validation_status=VALIDATION_STATUS_PROBE_FAILED,
            checksum=checksum,
            validation_error=str(exc),
        )

    if probe.duration_s < min_duration_s:
        return ValidationResult(
            record=record,
            validation_status=VALIDATION_STATUS_TOO_SHORT,
            duration_s=probe.duration_s,
            source_sample_rate_hz=probe.sample_rate_hz,
            checksum=checksum,
            validation_error=(
                f"Audio duration {probe.duration_s:.3f}s is below the "
                f"{min_duration_s:.3f}s minimum."
            ),
        )

    try:
        decoded_audio = decode_audio_pyav(
            file_path,
            target_sample_rate_hz=target_sample_rate_hz,
        )
    except Exception as exc:
        return ValidationResult(
            record=record,
            validation_status=VALIDATION_STATUS_DECODE_FAILED,
            duration_s=probe.duration_s,
            source_sample_rate_hz=probe.sample_rate_hz,
            checksum=checksum,
            validation_error=str(exc),
        )

    rms_db = compute_rms_db(decoded_audio.waveform)
    if rms_db < silence_threshold_db:
        return ValidationResult(
            record=record,
            validation_status=VALIDATION_STATUS_SILENT,
            duration_s=probe.duration_s,
            source_sample_rate_hz=probe.sample_rate_hz,
            checksum=checksum,
            decoded_audio=decoded_audio,
            rms_db=rms_db,
            validation_error=(
                f"Audio RMS {rms_db:.3f} dB is below the "
                f"{silence_threshold_db:.3f} dB silence threshold."
            ),
        )

    return ValidationResult(
        record=record,
        validation_status=VALIDATION_STATUS_VALIDATED,
        duration_s=probe.duration_s,
        source_sample_rate_hz=probe.sample_rate_hz,
        checksum=checksum,
        decoded_audio=decoded_audio,
        rms_db=rms_db,
    )
```

Thứ tự này là thứ tự sống còn:

1. `exists` trước `sha256_file()`, vì nếu hash đường dẫn không tồn tại thì bạn mất luôn semantic status `missing_file`, chỉ còn lại một exception thô.
2. `sha256_file()` trước `probe_audio()`, vì file có thể tồn tại nhưng probe hỏng; reject event lúc đó vẫn nên mang checksum của bytes đã tồn tại trên disk.
3. `probe` trước `decode`, vì `probe.duration_s < 1.0` là lý do loại rẻ nhất, không cần trả giá decode.
4. `silence` sau `decode`, vì RMS phải đo trên waveform canonical mono/32 kHz, không phải trên metadata duration hay container-level guess.

Hai vết sẹo đẻ ra block này:

- silent-track bug: có lúc team thử gate silence quá sớm ở container level, và kết quả là cùng một file nhưng pass/fail khác nhau sau downmix-resample.
- downmix bug: auto-downmix của FFmpeg làm amplitude drift so với legacy; test reference đã bắt được và ép sửa trong `shared/audio.py`.

Chạy verify đúng vào các mắt xích của chain:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_ingestion_pipeline.py -q -k "validation_reports_missing_file or validation_reports_decode_failure_after_successful_probe"
```

Nếu local workspace có legacy reference checkout, chạy thêm test semantic scar:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_reference_semantics.py -q -k "decode_audio_pyav_matches_legacy_downmix_resample_semantics"
```

Xanh ở đây nghĩa là bạn đã khóa được decision tree `missing_file / probe_failed / too_short / decode_failed / silent / validated` mà không lẫn lộn nguyên nhân lỗi.

---

### Bước 2.3. Mở `src/event_driven_audio_analytics/ingestion/modules/segmenter.py`; gõ sliding window math đúng đến dấu `>`

Đây là chỗ rất dễ “nhìn tưởng đơn giản” rồi phá semantic mà không hay.  
Mở `segmenter.py`, gõ `AudioSegment` trước, rồi gõ `segment_audio()`.

Math phải chốt ngay đầu hàm:

```text
N_seg = round(f_s * T_seg)
```

```text
N_hop = round(f_s * (T_seg - T_overlap))
```

```text
N_tail = lfloor f_s * T_tail_threshold rfloor
```

Với repo này:

```text
f_s = 32000, T_seg=3.0, T_overlap=1.5, T_tail_threshold=1.0
```

nên:

```text
N_seg = round(32000 * 3.0)=96000
```

```text
N_hop = round(32000 * (3.0-1.5))=48000
```

```text
N_tail = lfloor 32000 * 1.0 rfloor = 32000
```

Dòng code phải khớp từng công thức:

```python
def segment_audio(
    *,
    run_id: str,
    track_id: int,
    waveform: np.ndarray,
    sample_rate_hz: int,
    segment_duration_s: float = 3.0,
    segment_overlap_s: float = 1.5,
    tail_pad_threshold_s: float = 1.0,
) -> list[AudioSegment]:
    if waveform.ndim != 2 or waveform.shape[0] != 1:
        raise ValueError("Segmenter expects a mono waveform shaped as (1, samples).")

    segment_samples = int(round(sample_rate_hz * segment_duration_s))
    hop_samples = int(round(sample_rate_hz * (segment_duration_s - segment_overlap_s)))
    tail_pad_threshold_samples = int(math.floor(sample_rate_hz * tail_pad_threshold_s))
    if hop_samples <= 0:
        raise ValueError("segment_overlap_s must be smaller than segment_duration_s.")

    total_samples = waveform.shape[-1]
    segments: list[AudioSegment] = []
    start = 0
    segment_idx = 0
    while start + segment_samples <= total_samples:
        segments.append(
            AudioSegment(
                run_id=run_id,
                track_id=track_id,
                segment_idx=segment_idx,
                waveform=waveform[:, start : start + segment_samples].copy(),
                sample_rate=sample_rate_hz,
                duration_s=segment_duration_s,
                is_last_segment=False,
            )
        )
        start += hop_samples
        segment_idx += 1

    remaining_samples = total_samples - start
    if remaining_samples > tail_pad_threshold_samples:
        tail_segment = waveform[:, start:].copy()
        pad_width = segment_samples - tail_segment.shape[-1]
        if pad_width > 0:
            tail_segment = np.pad(tail_segment, ((0, 0), (0, pad_width)))

        segments.append(
            AudioSegment(
                run_id=run_id,
                track_id=track_id,
                segment_idx=segment_idx,
                waveform=tail_segment,
                sample_rate=sample_rate_hz,
                duration_s=segment_duration_s,
                is_last_segment=False,
            )
        )

    if segments:
        segments[-1].is_last_segment = True

    return segments
```

Ở đây có ba guard mà nếu bỏ đi thì bug sẽ đến muộn và rất khó lần:

- Guard 1: `waveform.shape[0] != 1` thì nổ ngay. Segmenter không nhận stereo; stereo phải chết hoặc được canonicalize ở `decode_audio_pyav()`.
- Guard 2: `hop_samples <= 0` thì nổ ngay. Nếu `segment_overlap_s >= segment_duration_s`, vòng lặp sẽ không tiến.
- Guard 3: tail rule dùng **`>`**, không phải `>=`.

Lý do dấu `>` là semantic, không phải style.  
Legacy rule là “phần dư phải **lớn hơn** 1.0 giây mới được pad thành segment cuối”.  
Nếu bạn đổi thành `>=`, một tail đúng bằng `32000` samples cũng thành segment, và count sẽ lệch toàn bộ boundary matrix.

Ví dụ:

- `1.00 s` đúng bằng `32000` samples: với `>` thì không tạo segment; với `>=` thì tạo sai thêm 1 segment.
- `1.01 s`: `32320 > 32000`, nên tạo 1 padded segment.
- `29.95 s`: current path ra `19` segment.
- `30.6 s`: current path ra `20` segment.

Tức là count không phải trực giác “chia đều là xong”. Nó là:

```text
count = count_full_windows + 1(remaining > N_tail)
```

Chuyện `.copy()` ở slice không phải phí RAM vô cớ. Nó là boundary ownership:

```python
waveform=waveform[:, start : start + segment_samples].copy()
```

Nếu bỏ `.copy()`:

- mỗi `AudioSegment` chỉ cầm view vào buffer lớn của toàn track;
- buffer lớn đó bị pin sống tới khi segment cuối cùng biến mất;
- bất kỳ biến đổi in-place nào ở bước sau đều có thể làm các segment share base bất ngờ;
- lỗi kiểu “PyAV borrowed reference / buffer lifetime” sẽ quay lại dưới hình thức aliasing khó đoán.

Current path cố tình khóa ownership ở hai lớp:

1. `shared/audio.py` gom frame PyAV thành một NumPy waveform owned.
2. `segmenter.py` cắt từng segment thành buffer owned riêng bằng `.copy()`.

Vết sẹo buộc phải giữ rule này:

- count drift ở biên 1.0s khi ai đó đổi `>` thành `>=` vì nghĩ “inclusive đẹp hơn”.
- memory/pathology bug khi segment giữ view vào whole-track buffer, khiến debug artifact writer nhìn như lỗi I/O nhưng gốc thật là buffer aliasing.

Gõ xong bước này, chạy đúng test biên:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_ingestion_pipeline.py -q -k "segment_count_matches_30s_and_tail_padding_rules or duration_boundary_sample_matrix_matches_expected_segment_counts"
```

Nếu hai test này đỏ, đừng chạm `artifact_writer.py`. Segment count sai thì manifest, event count, metric count đều sai dây chuyền.

---

### Bước 2.4. Mở `src/event_driven_audio_analytics/ingestion/modules/artifact_writer.py`; gõ claim-check write path theo đúng luật `WAV -> Checksum -> Manifest -> Publish`

Đừng mở `pipeline.py` trước.  
Muốn orchestrator publish đúng, ta phải có primitive viết artifact đúng đã.

Mở thêm `src/event_driven_audio_analytics/shared/storage.py` để khóa path grammar trước:

```python
def run_root(artifacts_root: Path, run_id: str) -> Path:
    return artifacts_root / "runs" / run_id


def segment_artifact_uri(artifacts_root: Path, run_id: str, track_id: int, segment_idx: int) -> str:
    return _as_uri(
        run_root(artifacts_root, run_id) / "segments" / str(track_id) / f"{segment_idx}.wav"
    )


def manifest_uri(artifacts_root: Path, run_id: str) -> str:
    return _as_uri(run_root(artifacts_root, run_id) / "manifests" / "segments.parquet")
```

Identity logic ở đây là:

```text
k_segment = (run_id, track_id, segment_idx)
```

Và claim-check invariant là:

```text
Kafka event => pointer nhỏ
```

```text
artifact bytes not in Kafka
```

Quay lại `artifact_writer.py`, gõ `SegmentDescriptor` và `MANIFEST_REQUIRED_FIELDS` trước.  
Chúng là hàng rào contract giữa ingestion và processing:

```python
MANIFEST_REQUIRED_FIELDS = (
    "run_id",
    "track_id",
    "segment_idx",
    "artifact_uri",
    "checksum",
    "manifest_uri",
    "sample_rate",
    "duration_s",
    "is_last_segment",
)


@dataclass(slots=True)
class SegmentDescriptor:
    run_id: str
    track_id: int
    segment_idx: int
    artifact_uri: str
    checksum: str
    manifest_uri: str
    sample_rate: int
    duration_s: float
    is_last_segment: bool
```

Block core là `write_segment_artifacts()`. Viết theo đúng thứ tự sau, không đảo:

1. xác định `manifest_uri`
2. đảm bảo layout thư mục tồn tại
3. ghi từng file WAV
4. hash từng file WAV vừa ghi
5. dựng descriptor
6. append/collapse manifest theo natural key
7. verify manifest consistency
8. trả descriptor ra cho orchestrator publish event

Code:

```python
def write_segment_artifacts(
    artifacts_root: Path,
    segments: list[AudioSegment],
) -> list[SegmentDescriptor]:
    if not segments:
        return []

    run_id = segments[0].run_id
    manifest_uri_str = manifest_uri(artifacts_root, run_id)
    manifest_path = Path(manifest_uri_str)
    ensure_artifact_layout(artifacts_root, run_id)

    descriptors: list[SegmentDescriptor] = []
    for segment in segments:
        artifact_uri_str = segment_artifact_uri(
            artifacts_root,
            segment.run_id,
            segment.track_id,
            segment.segment_idx,
        )
        artifact_path = Path(artifact_uri_str)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        _write_wav_mono(artifact_path, segment.waveform, segment.sample_rate)
        descriptors.append(
            SegmentDescriptor(
                run_id=segment.run_id,
                track_id=segment.track_id,
                segment_idx=segment.segment_idx,
                artifact_uri=artifact_uri_str,
                checksum=sha256_file(artifact_path),
                manifest_uri=manifest_uri_str,
                sample_rate=segment.sample_rate,
                duration_s=segment.duration_s,
                is_last_segment=segment.is_last_segment,
            )
        )

    current_frame = _manifest_frame(descriptors)
    if manifest_path.exists():
        existing_frame = pl.read_parquet(manifest_path)
        current_frame = (
            pl.concat([existing_frame, current_frame], how="vertical_relaxed")
            .unique(subset=["run_id", "track_id", "segment_idx"], keep="last")
            .sort(["run_id", "track_id", "segment_idx"])
        )

    current_frame.write_parquet(manifest_path)
    verify_manifest_consistency(descriptors)
    return descriptors
```

Thứ tự này là thứ tự sống còn:

```text
publishable(s)
<=>
exists(wav_s)
and
sha256(wav_s)=checksum_s
and
manifest[k_s]=descriptor_s
```

Nếu bạn viết manifest trước rồi mới ghi WAV, bạn có thể tạo ra row hợp lệ về schema nhưng trỏ tới file chưa tồn tại.  
Nếu bạn publish event trước khi `verify_manifest_consistency()` chạy xong, processing có thể thắng race và mở manifest/artifact trong trạng thái chưa nhất quán.

Một bug rất hay bị dính: hash nhầm **source MP3** thay vì **written WAV artifact**.  
Ở repo này, `processing` sẽ đọc `artifact_uri` là file WAV đã qua PCM16 round-trip. Vậy checksum đúng phải là:

```text
checksum = sha256(written WAV bytes)
```

không phải:

```text
sha256(source MP3 bytes)
```

Nếu hash nhầm nguồn, toàn bộ claim-check verification phía sau sẽ fail dù audio nghe có vẻ vẫn phát được.

`verify_manifest_consistency()` là block guard sinh ra từ đúng nỗi đau đó:

```python
def verify_manifest_consistency(descriptors: list[SegmentDescriptor]) -> None:
    if not descriptors:
        return

    manifest_uris = {descriptor.manifest_uri for descriptor in descriptors}
    if len(manifest_uris) != 1:
        raise ValueError("Segment descriptors must share exactly one manifest_uri.")

    manifest_path = Path(next(iter(manifest_uris)))
    manifest_frame = read_manifest_frame(manifest_path)

    for descriptor in descriptors:
        artifact_path = Path(descriptor.artifact_uri)
        if not artifact_path.exists():
            raise FileNotFoundError(
                f"Segment artifact does not exist: {artifact_path.as_posix()}"
            )

        actual_checksum = sha256_file(artifact_path)
        if actual_checksum != descriptor.checksum:
            raise ValueError(
                "Segment artifact checksum does not match its descriptor "
                f"for track_id={descriptor.track_id} segment_idx={descriptor.segment_idx}."
            )
```

Chạy verify đúng vào claim-check boundary:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_ingestion_pipeline.py -q -k "manifest or artifact"
```

Muốn check full descriptor/manifest shape:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_ingestion_pipeline.py -q -k "MANIFEST_REQUIRED_FIELDS or process_record_on_valid_track"
```

Khi bước này xanh, bạn mới có quyền nói “artifact side của claim-check đã publishable”.

---

### Bước 2.5. Mở `src/event_driven_audio_analytics/ingestion/pipeline.py` và `publisher.py`; gõ orchestration theo đúng luật publish order

Giờ mới mở orchestrator.  
Mục tiêu ở đây không phải viết một hàm dài cho đã. Mục tiêu là giữ cho mọi nhánh lỗi đều ra được trạng thái logic trung thực:

- track hợp lệ: có artifact, có manifest, có `audio.metadata`, có `audio.segment.ready`
- track bị reject: chỉ có `audio.metadata`
- track validation pass nhưng segment count bằng `0`: vẫn chỉ có `audio.metadata`, nhưng `validation_status=no_segments`

Mở `publisher.py` trước và gõ ba builder/hai publisher theo key semantics rõ ràng:

```python
def build_metadata_event(payload: AudioMetadataPayload) -> EventEnvelope[AudioMetadataPayload]:
    return build_envelope(event_type="audio.metadata", source_service="ingestion", payload=payload)


def build_segment_ready_event(
    payload: AudioSegmentReadyPayload,
) -> EventEnvelope[AudioSegmentReadyPayload]:
    return build_envelope(
        event_type="audio.segment.ready",
        source_service="ingestion",
        payload=payload,
    )


def publish_metadata_event(
    producer: ProducerLike,
    payload: AudioMetadataPayload,
    *,
    delivery_timeout_s: float = 30.0,
) -> EventEnvelope[AudioMetadataPayload]:
    envelope = build_metadata_event(payload)
    produce_and_wait(
        producer,
        topic=AUDIO_METADATA,
        key=str(payload.track_id).encode("utf-8"),
        value=serialize_envelope(envelope),
        timeout_s=delivery_timeout_s,
    )
    return envelope
```

Guard ở đây là key:

- `audio.metadata` key theo `track_id`
- `audio.segment.ready` key theo `track_id`
- `system.metrics` key theo `service_name`

Đừng “tiện tay” key metadata theo `run_id`. Unit smoke đã khóa bug drift đó.

Quay sang `pipeline.py`, gõ `_build_metadata_payload()` trước `process_record()`.  
Hàm này là chỗ cứu schema-valid cho reject path:

```python
def _build_metadata_payload(
    self,
    record: MetadataRecord,
    validation: ValidationResult,
    *,
    manifest_uri_value: str | None = None,
) -> AudioMetadataPayload:
    duration_s = validation.duration_s
    if duration_s is None or duration_s <= 0.0:
        duration_s = record.declared_duration_s
    if duration_s is None or duration_s <= 0.0:
        raise ValueError(
            "audio.metadata requires a positive duration_s for "
            f"track_id={record.track_id}, but neither validation nor metadata ETL "
            "produced one."
        )

    payload_kwargs: dict[str, Any] = {
        "run_id": self.settings.base.run_id,
        "track_id": record.track_id,
        "artist_id": record.artist_id,
        "genre": record.genre_label,
        "source_audio_uri": record.source_audio_uri,
        "validation_status": validation.validation_status,
        "duration_s": duration_s,
        "subset": record.subset,
        "checksum": validation.checksum,
    }
    if manifest_uri_value is not None:
        payload_kwargs["manifest_uri"] = manifest_uri_value
    return AudioMetadataPayload(**payload_kwargs)
```

Tại sao reject path vẫn publish metadata-only?  
Vì reject cũng là dữ liệu hệ thống. PoC này không chỉ chứng minh “xử lý track đẹp”. Nó còn chứng minh pipeline có thể nói thật về track bị loại:

```text
validation_status != validated => publish audio.metadata only
```

và:

```text
nexists artifact => không được bịa manifest_uri
```

Tức là reject path phải **không có** `manifest_uri`. Nếu bạn nhét `manifest_uri` vào metadata của track reject, downstream sẽ coi như có claim-check hợp lệ và cố mở file không tồn tại.

Giờ gõ `process_record()` theo đúng thứ tự sau:

1. validate
2. `nếu reject -> publish metadata-only -> return`
3. segment
4. `nếu not segments -> đổi status thành no_segments -> publish metadata-only -> return`
5. write artifacts
6. publish `audio.metadata`
7. publish toàn bộ `audio.segment.ready`

Code sống còn:

```python
def process_record(
    self,
    producer: ProducerLike,
    record: MetadataRecord,
) -> TrackIngestionResult:
    validation = validate_audio_record(
        record,
        target_sample_rate_hz=self.settings.target_sample_rate_hz,
        min_duration_s=self.settings.min_duration_s,
        silence_threshold_db=self.settings.silence_threshold_db,
    )
    if validation.validation_status != VALIDATION_STATUS_VALIDATED or validation.decoded_audio is None:
        metadata_event = publish_metadata_event(
            producer,
            self._build_metadata_payload(record, validation),
            delivery_timeout_s=self.settings.producer_delivery_timeout_ms / 1000.0,
        )
        return TrackIngestionResult(
            record=record,
            validation=validation,
            metadata_event=metadata_event,
            segment_descriptors=[],
            segment_events=[],
            artifact_write_ms=0.0,
        )

    segments = segment_audio(
        run_id=self.settings.base.run_id,
        track_id=record.track_id,
        waveform=validation.decoded_audio.waveform,
        sample_rate_hz=validation.decoded_audio.sample_rate_hz,
        segment_duration_s=self.settings.segment_duration_s,
        segment_overlap_s=self.settings.segment_overlap_s,
    )
    if not segments:
        validation = replace(
            validation,
            validation_status=VALIDATION_STATUS_NO_SEGMENTS,
            validation_error=(
                "Decoded audio passed validation but did not yield any legal "
                "3.0-second segments under the legacy tail-padding rule."
            ),
        )
        metadata_event = publish_metadata_event(
            producer,
            self._build_metadata_payload(record, validation),
            delivery_timeout_s=self.settings.producer_delivery_timeout_ms / 1000.0,
        )
        return TrackIngestionResult(
            record=record,
            validation=validation,
            metadata_event=metadata_event,
            segment_descriptors=[],
            segment_events=[],
            artifact_write_ms=0.0,
        )

    segment_descriptors = write_segment_artifacts(
        self.settings.base.artifacts_root,
        segments,
    )
    metadata_event = publish_metadata_event(
        producer,
        self._build_metadata_payload(
            record,
            validation,
            manifest_uri_value=segment_descriptors[0].manifest_uri,
        ),
        delivery_timeout_s=self.settings.producer_delivery_timeout_ms / 1000.0,
    )
    segment_events = [
        publish_segment_ready_event(
            producer,
            AudioSegmentReadyPayload(
                run_id=descriptor.run_id,
                track_id=descriptor.track_id,
                segment_idx=descriptor.segment_idx,
                artifact_uri=descriptor.artifact_uri,
                checksum=descriptor.checksum,
                sample_rate=descriptor.sample_rate,
                duration_s=descriptor.duration_s,
                is_last_segment=descriptor.is_last_segment,
                manifest_uri=descriptor.manifest_uri,
            ),
            delivery_timeout_s=self.settings.producer_delivery_timeout_ms / 1000.0,
        )
        for descriptor in segment_descriptors
    ]
```

Lý do phải publish `audio.metadata` trước `audio.segment.ready`:

```text
artifact < manifest < audio.metadata < audio.segment.ready_i
```

Giải thích kiểu IDE:

- `audio.metadata` là track-level context: ai, thuộc subset nào, validation status gì, source ở đâu.
- `audio.segment.ready` chỉ là per-segment pointer.
- pointer mà đi trước context thì downstream có thể nhìn thấy segment hợp lệ nhưng chưa có track state tương ứng.
- current code không có cross-topic transaction magic; vì vậy ít nhất local producer order phải đi từ context trước, pointer sau.

Nói thẳng hơn: metadata thiếu segment còn chấp nhận được như trạng thái “track đã biết nhưng chưa xử lý xong”. Segment đi trước metadata là trạng thái xấu hơn: downstream nhận con trỏ nhưng chưa có định danh track-level đầy đủ trong narrative hệ thống.

Vết sẹo đẻ ra block này:

- reject-path bug: trước đây có xu hướng “track lỗi thì bỏ luôn khỏi stream”, làm dashboard và writer không phân biệt được “không chọn track” với “đã chọn nhưng bị loại”.
- manifest ghost bug: một số nhánh lỗi vẫn bơm `manifest_uri=None` hoặc bịa path string, khiến downstream fail muộn khi mở file.
- key drift bug: message được bắn đúng payload nhưng sai key, smoke verifier bắt ngay vì `audio.metadata` phải keyed by `track_id`.

Mở `src/event_driven_audio_analytics/shared/kafka.py` và giữ producer config này nguyên trạng:

```python
def producer_config(
    bootstrap_servers: str,
    client_id: str,
    *,
    retries: int = 10,
    retry_backoff_ms: int = 250,
    retry_backoff_max_ms: int = 5_000,
    delivery_timeout_ms: int = 120_000,
) -> dict[str, object]:
    return {
        "bootstrap.servers": bootstrap_servers,
        "client.id": client_id,
        "enable.idempotence": True,
        "acks": "all",
        "retries": retries,
        "retry.backoff.ms": retry_backoff_ms,
        "retry.backoff.max.ms": retry_backoff_max_ms,
        "delivery.timeout.ms": delivery_timeout_ms,
    }
```

`enable.idempotence=True` ở producer **không** thay thế end-to-end idempotent sink ở writer.  
Nó chỉ đảm bảo retry produce ít làm bẩn stream hơn ở phía broker. Còn logic “cùng `run_id, track_id, segment_idx` không nhân bản row” vẫn là bài toán downstream.

Cuối cùng mới gõ `run()`. Ở đây có ba thứ phải đi cùng nhau: preflight, run-total metrics, flush guard.

```python
def run(self, producer: ProducerLike | None = None) -> list[TrackIngestionResult]:
    own_producer = producer is None
    logger = self._service_logger()
    active_producer = producer

    try:
        wait_for_runtime_dependencies(self.settings, logger)
        if active_producer is None:
            active_producer = build_producer(
                bootstrap_servers=self.settings.base.kafka_bootstrap_servers,
                client_id=f"{self.settings.base.service_name}-producer",
                retries=self.settings.producer_retries,
                retry_backoff_ms=self.settings.producer_retry_backoff_ms,
                retry_backoff_max_ms=self.settings.producer_retry_backoff_max_ms,
                delivery_timeout_ms=self.settings.producer_delivery_timeout_ms,
            )

        metrics = IngestionRunMetrics()
        results: list[TrackIngestionResult] = []
        for record in self.load_metadata_records():
            result = self.process_record(active_producer, record)
            metrics.record_track(
                segment_count=len(result.segment_events),
                validation_failed=result.validation.validation_status != VALIDATION_STATUS_VALIDATED,
                artifact_write_ms=result.artifact_write_ms,
            )
            results.append(result)

        for payload in metrics.as_payloads(
            run_id=self.settings.base.run_id,
            service_name=self.settings.base.service_name,
        ):
            publish_system_metric_event(
                active_producer,
                payload,
                delivery_timeout_s=self.settings.producer_delivery_timeout_ms / 1000.0,
            )

        remaining_messages = active_producer.flush()
        if remaining_messages not in (0, None):
            raise RuntimeError(
                "Ingestion finished with undelivered Kafka messages still queued."
            )
        return results
    finally:
        if own_producer and active_producer is not None:
            active_producer.flush()
```

Run-level metrics ở đây là:

```text
tracks_total = sum_i 1
```

```text
segments_total = sum_i |segments_i|
```

```text
validation_failures = sum_i 1(status_i != validated)
```

```text
artifact_write_ms = sum_i t^artifact_i
```

Chúng được publish cuối run với `labels_json={"scope": "run_total"}`. Đừng đổi scope thành `per_track`; smoke verifier đã khóa bug drift đó.

Preflight cũng không được bỏ. `wait_for_runtime_dependencies()` kiểm tra:

- required topics đã có thật
- `ARTIFACTS_ROOT` writable
- `METADATA_CSV_PATH` readable
- `AUDIO_ROOT_PATH` readable
- run-scoped `segments/` và `manifests/` tồn tại và writable
- track-scoped segment directories cho population đang chọn có thể probe-write được

Nó tồn tại vì một lỗi kinh điển là “pipeline chết giữa chừng rồi mới phát hiện manifest path bị chặn bởi file”. Lúc đó event có thể đã bắn một phần rồi.

Chạy verify đúng vào orchestration hot path:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_ingestion_pipeline.py -q -k "process_record or run_metrics or producer_config"
```

Rồi khóa smoke semantics:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_ingestion_smoke_verify.py -q
```

Muốn kiểm readiness riêng:

```powershell
docker compose run --rm --no-deps ingestion python -m event_driven_audio_analytics.ingestion.app preflight
```

Đến đây, ingestion pipeline đã có đủ bốn lớp sống còn:

1. metadata population được khóa đúng subset
2. validation path ra quyết định đúng thứ tự `exists -> hash -> probe -> duration -> decode -> silence`
3. segment math giữ đúng legacy counts với tail rule `>`
4. claim-check chỉ publish sau khi `WAV -> checksum -> manifest -> verify` đã hoàn tất

Dừng ở đây. CHUNK 2 kết thúc tại ingestion pipeline.

# CHUNK 3

**Phase 3 — Xây Dựng Processing Pipeline**

### Bước 3.1. Mở `src/event_driven_audio_analytics/processing/modules/artifact_loader.py`, rồi nhìn sang `src/event_driven_audio_analytics/processing/pipeline.py::_validate_loaded_artifact`

Gõ `LoadedSegmentArtifact` trước. Sau đó gõ `_decode_pcm_frames()` và `load_segment_artifact()`.  
Đừng mở `log_mel.py` trước. Processing đúng bắt đầu từ luật claim-check payload (event chỉ mang pointer + checksum, không mang waveform bytes).

Luật ở đây là:

```text
safe_to_decode(artifact)=
[sha256(artifact)=checksum_event]
```

không phải:

```text
decode trước -> hash sau
```

Gõ block core như sau:

```python
def load_segment_artifact(
    artifact_uri: str,
    checksum: str,
    *,
    expected_sample_rate_hz: int | None = None,
) -> LoadedSegmentArtifact:
    artifact_path = Path(artifact_uri)
    if not artifact_path.exists():
        raise FileNotFoundError(f"Segment artifact does not exist: {artifact_path.as_posix()}")

    actual_checksum = sha256_file(artifact_path)
    if actual_checksum != checksum:
        raise ArtifactChecksumMismatch(
            "Segment artifact checksum mismatch "
            f"expected={checksum} actual={actual_checksum} "
            f"path={artifact_path.as_posix()}"
        )

    with wave.open(str(artifact_path), "rb") as handle:
        if handle.getnchannels() != 1:
            raise ArtifactLoadError(
                "Segment artifact must be mono after ingestion normalization."
            )
        if handle.getcomptype() != "NONE":
            raise ArtifactLoadError(
                "Segment artifact must use uncompressed PCM WAV framing."
            )

        sample_rate_hz = int(handle.getframerate())
        if expected_sample_rate_hz is not None and sample_rate_hz != expected_sample_rate_hz:
            raise ArtifactLoadError(
                "Segment artifact sample rate does not match the claim-check event "
                f"expected={expected_sample_rate_hz} actual={sample_rate_hz}"
            )

        frame_count = int(handle.getnframes())
        waveform = _decode_pcm_frames(
            frames=handle.readframes(frame_count),
            sample_width=handle.getsampwidth(),
        )

    duration_s = frame_count / float(sample_rate_hz)
    return LoadedSegmentArtifact(
        artifact_uri=artifact_uri,
        artifact_path=artifact_path,
        checksum=actual_checksum,
        waveform=waveform,
        sample_rate_hz=sample_rate_hz,
        duration_s=duration_s,
    )
```

Tại sao phải check `sha256` trước khi giải mã WAV? Vì claim-check là boundary bảo toàn identity của bytes. Nếu decode trước rồi mới hash, bạn đang tiêu CPU vào một file chưa được xác thực, và nếu file bị rách hoặc bị thay thế, mọi DSP phía sau sẽ chạy trên dữ liệu sai nguồn.

Guard ở block này có bốn lớp:

- `exists` trước mọi thứ, để phân biệt rõ `artifact_not_ready` với lỗi decode nội dung.
- `sha256_file()` trước `wave.open()`, để mismatch checksum bị chặn ở boundary bytes.
- `getnchannels() == 1`, vì ingestion đã normalize mono; processing không được tự downmix lại.
- `getcomptype() == "NONE"`, vì runtime path khóa WAV PCM không nén.

Sau đó mới cross-check metadata của event với file vật lý. Block này nằm ở `pipeline.py`, không nằm trong loader, vì đây là bước đối chiếu giữa hai nguồn sự thật: envelope và file đã load.

```python
def _validate_loaded_artifact(self, payload: AudioSegmentReadyPayload, artifact: LoadedSegmentArtifact) -> None:
    if artifact.sample_rate_hz != payload.sample_rate:
        raise ArtifactLoadError(
            "audio.segment.ready sample_rate does not match the claim-check artifact "
            f"expected={payload.sample_rate} actual={artifact.sample_rate_hz}"
        )

    max_duration_delta_s = 1.0 / float(payload.sample_rate)
    if abs(artifact.duration_s - payload.duration_s) > max_duration_delta_s:
        raise ArtifactLoadError(
            "audio.segment.ready duration_s does not match the claim-check artifact "
            f"expected={payload.duration_s} actual={artifact.duration_s}"
        )
```

Math ở đây là tolerance theo đúng một sample:

```text
Delta_max = (1 / f_s)
```

Với `f_s = 32000`:

```text
Delta_max = (1 / 32000) ~ 31.25 mu s
```

Code:

```python
max_duration_delta_s = 1.0 / float(payload.sample_rate)
```

Tại sao không so `duration_s` bằng tuyệt đối? Vì duration trong event là số thực suy ra từ sample count, và file vật lý cũng suy ra lại từ sample count. Sai khác cỡ một sample là chấp nhận được; sai hơn thế là drift contract, không phải noise.

Vết sẹo đẻ ra block này là claim-check drift: event nói một `checksum/sample_rate/duration`, file trên disk lại là một thứ khác. Nếu không chặn ở đây, `rms.py`, `log_mel.py`, `welford.py` sẽ chạy đúng thuật toán trên sai artifact.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_pipeline.py -q -k "segment_loader_reads_claim_check_artifact or segment_loader_rejects_checksum_mismatch"
```

Muốn verify mapping failure class ở runtime loop:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_runtime.py -q -k "artifact_not_ready or checksum_mismatch"
```

---

### Bước 3.2. Mở `src/event_driven_audio_analytics/processing/modules/rms.py` và `silence_gate.py`

Gõ `RmsSummary`, rồi `summarize_rms()`, rồi `encode_rms_db_for_event()`. Sau đó mới gõ `is_silent_segment()`.

Toán học cốt lõi:

```text
RMS(x)=sqrt((1 / N)sum_n=1^Nx_n^2)
```

```text
RMS_dBFS(x)=20log_10(RMS(x))
```

Với digital silence:

```text
RMS(x)=0 => RMS_dBFS(x)=-inf
```

Code phải giữ sự thật toán học này ở state nội bộ:

```python
def summarize_rms(waveform: np.ndarray) -> RmsSummary:
    mono_waveform = waveform.astype(np.float32, copy=False)
    if mono_waveform.size == 0:
        return RmsSummary(rms_linear=0.0, rms_dbfs=-math.inf)

    rms_linear = float(np.sqrt(np.mean(np.square(mono_waveform), dtype=np.float64)))
    return RmsSummary(rms_linear=rms_linear, rms_dbfs=compute_rms_db(mono_waveform))
```

Nhưng envelope `audio.features` lại phải chở số JSON-safe. Ở đây nảy ra conflict toán học:

- RMS thật của silent segment là `-inf`
- Transport JSON không nên mang non-finite number
- Contract event đang khóa `rms` là số hữu hạn

Repo giải bài toán này bằng cách **không sửa toán**, chỉ clamp ở transport:

```python
def encode_rms_db_for_event(rms_dbfs: float, *, floor_db: float) -> float:
    if math.isfinite(rms_dbfs):
        return rms_dbfs
    return floor_db
```

Và orchestrator gọi đúng ở chỗ build payload:

```python
rms=encode_rms_db_for_event(
    rms_summary.rms_dbfs,
    floor_db=self.settings.silence_threshold_db,
),
```

Nói ngắn:

```text
DSP truth = -inf
```

```text
transport value = -60.0
```

Hai giá trị này không được nhập nhằng. Nếu bạn overwrite luôn `rms_summary.rms_dbfs = -60.0`, bạn đã làm sai state nội bộ để chiều lòng transport.

Silence gate cũng không dùng RMS clamp để quyết định im lặng. Nó dùng log-mel variance sau transform:

```python
def is_silent_segment(mel: torch.Tensor, *, std_floor: float = 1e-7) -> bool:
    if mel.ndim != 3 or mel.shape[0] != 1:
        raise ValueError("Silence gate expects a log-mel tensor shaped as (1, n_mels, frames).")

    return bool(mel.std().item() < std_floor)
```

Tức là:

```text
silent = indicator[std(mel) < 10^-7]
```

Tại sao lại gate trên `mel.std()` thay vì RMS? Vì legacy path khóa silence decision sau log-mel, không phải ở waveform RMS. Một waveform có năng lượng cực thấp có thể chạm floor khác với một mel tensor gần hằng; repo này chọn bám legacy semantics, không chọn “đơn giản hóa”.

Guard phải giữ:

- `summarize_rms()` trả `-inf` thật cho silence.
- `encode_rms_db_for_event()` chỉ chạy ở transport boundary.
- `is_silent_segment()` nhận đúng shape `(1, n_mels, frames)`.
- `silence_threshold_db=-60.0` chỉ là floor vận chuyển, không phải phép thế chỗ cho `-inf` trong DSP math.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_pipeline.py -q -k "rms_summary_matches_expected_dbfs_for_tone_fixture or processing_pipeline_marks_silent_fixture_and_clamps_transport_rms"
```

---

### Bước 3.3. Mở `src/event_driven_audio_analytics/processing/modules/log_mel.py`

Gõ `LogMelExtractor.__post_init__()` trước để khóa transform parameters, rồi mới gõ `compute()`.

STFT (Short-Time Fourier Transform, biến đổi Fourier ngắn hạn) ở đây được hiện thực bởi `torchaudio.transforms.MelSpectrogram`. Toán học của nó vẫn phải được khóa vì code đang đóng băng đúng legacy parameter set:

```text
X[m,k] = sum_n=0^N_fft-1 x[n+mH] w[n] e^-j2pi_kn/N_fft
```

Trong đó:

- `N_fft = 1024`
- `H = hop_length = 320`

Sau đó power spectrogram đi qua mel filter bank:

```text
P[m,k] = |X[m,k]|^2
```

```text
M[b,m] = sum_k H_b[k] P[m,k]
```

và log-mel:

```text
L[b,m] = log(M[b,m] + epsilon)
```

với:

- `b in {1,...,128}`
- `epsilon = 10^-9`

Code khóa đúng các tham số đó ở `__post_init__()`:

```python
def __post_init__(self) -> None:
    self._device = torch.device(self.device)
    self._transform = torchaudio.transforms.MelSpectrogram(
        sample_rate=self.sample_rate_hz,
        n_mels=self.n_mels,
        n_fft=self.n_fft,
        hop_length=self.hop_length,
        f_min=self.f_min,
        f_max=self.f_max,
        norm="slaney",
        mel_scale="slaney",
    ).to(self._device)
```

Rồi `compute()` phải ép shape đích `(1, 128, 300)` bằng truncate hoặc pad, không mặc cho mỗi segment có frame count tự do:

```python
def compute(self, waveform: np.ndarray) -> torch.Tensor:
    if waveform.ndim != 2 or waveform.shape[0] != 1:
        raise ValueError("Log-mel extraction expects a mono waveform shaped as (1, samples).")

    segment = torch.from_numpy(waveform.copy()).float().to(self._device)
    mel = self._transform(segment)
    mel = torch.log(mel + self.log_epsilon)

    if mel.shape[-1] > self.target_frames:
        mel = mel[:, :, : self.target_frames]
    elif mel.shape[-1] < self.target_frames:
        pad_width = self.target_frames - mel.shape[-1]
        mel = torch.nn.functional.pad(mel, (0, pad_width))

    mel = mel.cpu()
    if tuple(int(dimension) for dimension in mel.shape) != self.expected_shape:
        raise ValueError(
            "Log-mel extractor failed to produce the locked shape "
            f"expected={self.expected_shape} actual={tuple(int(d) for d in mel.shape)}"
        )
    return mel
```

Toán học của phần ép shape là:

```text
F_out =
- F_in[:, :, 1:300], khi T_in > 300
- pad(F_in, 300 - T_in), khi T_in < 300
- F_in, khi T_in=300
```

Tức là target shape là contract, không phải observation.

Tại sao phải `waveform.copy()` trước `torch.from_numpy()`? Vì processing không được giữ reference chia sẻ với buffer loader phía trước rồi đẩy tensor vào transform graph. Đây là một guard ownership nữa: NumPy buffer này phải thuộc trọn segment hiện tại.

Guard của block này:

- `waveform.shape == (1, samples)`, không nhận stereo hay 1-D mơ hồ.
- `norm="slaney"` và `mel_scale="slaney"` phải khóa cùng legacy transform.
- `pad/truncate` phải xảy ra trước khi rời `compute()`.
- `expected_shape` phải được assert, không được chỉ “hy vọng” torchaudio luôn ra 300 frames.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_pipeline.py -q -k "mel_bins or mel_frames"
```

Nếu local có legacy reference checkout:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_reference_semantics.py -q -k "audio_features_mapping_stays_summary_first_without_feature_uri"
```

---

### Bước 3.4. Mở `src/event_driven_audio_analytics/processing/modules/welford.py`

Gõ `WelfordState`, rồi `mel_bin_means()`, rồi `update_welford()`.

Ở repo này, Welford chạy trên vector 128 chiều, không chạy trên toàn tensor 3-D.  
Trước tiên phải collapse `(1, 128, 300)` thành một vector mean theo trục time:

```text
x_t in R^128, x_t[b] = (1 / 300)sum_m=1^300 L_t[b,m]
```

Code:

```python
def mel_bin_means(mel: torch.Tensor | np.ndarray) -> np.ndarray:
    if isinstance(mel, torch.Tensor):
        mel_tensor = mel.detach().cpu()
        if mel_tensor.ndim != 3 or mel_tensor.shape[0] != 1:
            raise ValueError("Welford updates expect a log-mel tensor shaped as (1, n_mels, frames).")
        return mel_tensor.squeeze(0).mean(dim=1).numpy().astype(np.float64, copy=False)

    mel_array = np.asarray(mel, dtype=np.float64)
    if mel_array.ndim != 3 or mel_array.shape[0] != 1:
        raise ValueError("Welford updates expect a log-mel tensor shaped as (1, n_mels, frames).")
    return mel_array[0].mean(axis=1)
```

Rồi mới cập nhật Welford vector-valued:

```text
n_t = n_t-1 + 1
```

```text
delta_t = x_t - mu_t-1
```

```text
mu_t = mu_t-1 + (delta_t / n_t)
```

```text
delta'_t = x_t - mu_t
```

```text
M2_t = M2_t-1 + delta_t elementwise* delta'_t
```

```text
Var_t = (M2_t / n_t - 1)
```

Ở đây `elementwise*` là nhân từng phần tử; tức là toàn bộ update diễn ra theo 128 bins song song.

Code phải bám đúng công thức đó:

```python
def update_welford(state: WelfordState, mel: torch.Tensor | np.ndarray) -> WelfordState:
    sample_mean = mel_bin_means(mel)
    if state.mean is None or state.m2 is None:
        mean = np.zeros_like(sample_mean, dtype=np.float64)
        m2 = np.zeros_like(sample_mean, dtype=np.float64)
        count = 0
    else:
        mean = state.mean.copy()
        m2 = state.m2.copy()
        count = state.count

    count += 1
    delta = sample_mean - mean
    mean = mean + (delta / float(count))
    delta2 = sample_mean - mean
    m2 = m2 + (delta * delta2)
    return WelfordState(count=count, mean=mean, m2=m2, ref=state.ref)
```

Tại sao phải `copy()` `state.mean` và `state.m2`? Vì đây là in-memory state (state RAM, chỉ sống trong process, mất khi restart), và current function phải trả về next state mới, không được mutate state cũ giữa đường. Nếu mutate in-place rồi publish fail ở bước sau, bạn đã làm RAM drift trước khi durability kịp xảy ra.

`ref` được build theo `run_id`:

```python
def build_welford_state_ref(run_id: str) -> str:
    return f"welford:processing:v1:{run_id}:mel-bin-mean"
```

Guard của block này:

- shape input phải đúng `(1, n_mels, frames)`.
- `float64` cho mean/std path để tránh sai số tích lũy nhanh ở update online.
- không mutate `state` đầu vào; luôn trả `WelfordState` mới.
- scope theo `run_id`, không trộn nhiều run vào cùng một vector stats.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_pipeline.py -q -k "welford_updates_match_manual_per_bin_statistics or welford_state_stays_scoped_to_each_run_id"
```

Nếu muốn khóa shape trước Welford:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_pipeline.py -q -k "mel_bins and mel_frames"
```

---

### Bước 3.5. Mở `src/event_driven_audio_analytics/processing/pipeline.py`; giữ orchestrator thành micro-steps

Không được kể `process_payload()` như một hàm khổng lồ.  
Đọc nó như một chuỗi transition ngắn, mỗi transition chỉ được phép làm một việc.

#### Micro-step 3.5.1. Chặn event sai sample rate trước mọi I/O

```python
if payload.sample_rate != self.settings.target_sample_rate_hz:
    raise ValueError(
        "audio.segment.ready sample_rate must match the locked processing target "
        f"expected={self.settings.target_sample_rate_hz} actual={payload.sample_rate}"
    )
```

Tại sao viết vậy: event contract đã khóa `32000 Hz`; nếu event sai ngay từ payload thì không có lý do gì mở file.

Guard chặn bug: event nói `44100` nhưng artifact lại là `32000`, hoặc ngược lại.  
Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_pipeline.py -q -k "rejects_non_32khz_segment_ready_event"
```

#### Micro-step 3.5.2. Load artifact qua claim-check boundary

```python
artifact = load_segment_artifact(
    payload.artifact_uri,
    payload.checksum,
    expected_sample_rate_hz=self.settings.target_sample_rate_hz,
)
```

Tại sao viết vậy: `payload` không mang waveform bytes; nó chỉ mang pointer/checksum. DSP chưa được chạy trước khi boundary này pass.

Guard chặn bug: `FileNotFoundError`, `ArtifactChecksumMismatch`, `ArtifactLoadError` được phân lớp rõ để retry policy phía run loop không lẫn.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_pipeline.py -q -k "segment_loader"
```

#### Micro-step 3.5.3. Cross-check event metadata với artifact vật lý

```python
self._validate_loaded_artifact(payload, artifact)
```

Tại sao viết vậy: loader mới chỉ xác thực bytes/file framing; bước này mới xác thực event đang nói cùng một artifact.

Guard chặn bug: mismatch `sample_rate` hoặc `duration_s` giữa event và file thật.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_pipeline.py -q -k "segment_loader_reads_claim_check_artifact"
```

#### Micro-step 3.5.4. Tính RMS, log-mel, silence gate, và next Welford candidate

```python
rms_summary = summarize_rms(artifact.waveform)
mel = self._mel_extractor.compute(artifact.waveform)
silent_flag = is_silent_segment(
    mel,
    std_floor=self.settings.segment_silence_floor,
)
next_welford_state = update_welford(
    self.welford_state_for(payload.run_id),
    mel,
)
```

Tại sao viết vậy: bước này chỉ sinh **candidate state**, chưa commit vào RAM toàn cục.

Guard chặn bug: nếu DSP nổ, `self._welford_state_by_run_id` vẫn chưa bị mutate.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_pipeline.py -q -k "welford_updates_match_manual_per_bin_statistics or processing_pipeline_marks_silent_fixture_and_clamps_transport_rms"
```

#### Micro-step 3.5.5. Tính next run-metrics snapshot, chưa ghi file và chưa đổi RAM

```python
current_run_metrics = self.run_metrics_for(payload.run_id)
next_run_metrics = current_run_metrics.with_recorded_success(
    track_id=payload.track_id,
    segment_idx=payload.segment_idx,
    silent_flag=silent_flag,
)
```

Tại sao viết vậy: `with_recorded_success()` trả snapshot mới mang tính replay-stable (idempotency, nghĩa là replay cùng logical segment vẫn hội tụ về cùng state) theo natural key `(track_id, segment_idx)`.

Guard chặn bug: replay cùng segment nhưng `silent_flag` khác sẽ nổ `ProcessingMetricsStateError`, không âm thầm ghi đè.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_pipeline.py -q -k "silent_ratio_recovers_from_persisted_run_state_after_restart or replayed_segment_keeps_silent_ratio_stable_after_restart"
```

#### Micro-step 3.5.6. Publish `audio.features`

```python
features_event = publish_audio_features_event(
    producer,
    self._build_audio_features_payload(
        payload,
        rms_summary=rms_summary,
        silent_flag=silent_flag,
        mel=mel,
        processing_ms=processing_ms,
    ),
    trace_id=trace_id,
    delivery_timeout_s=self._processing_delivery_timeout_s(),
)
```

Tại sao viết vậy: output business event phải ra trước khi nói tới state tiến triển; nếu feature publish fail thì segment chưa được coi là thành công.

Guard chặn bug: `feature_publish_failed` phải cắt flow trước khi bất kỳ state durable hay RAM nào advance.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_pipeline.py -q -k "welford_state_does_not_advance_when_feature_publish_fails"
```

#### Micro-step 3.5.7. Publish success metrics

```python
metric_events = self._publish_success_metrics(
    producer,
    trace_id=trace_id,
    metric_payloads=metric_payloads,
)
```

Tại sao viết vậy: `processing_ms` và `silent_ratio` là output observability cùng transaction logic với `audio.features`; nếu metrics publish fail, state vẫn chưa được coi là bền.

Guard chặn bug: `metric_publish_failed` phải chặn mọi update state phía sau.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_pipeline.py -q -k "run_metrics_do_not_advance_when_metric_publish_fails"
```

#### Micro-step 3.5.8. Persist `processing_metrics.json`

```python
if next_run_metrics is not current_run_metrics:
    self._persist_run_metrics(
        run_id=payload.run_id,
        run_metrics=next_run_metrics,
    )
```

Tại sao viết vậy: đây là durable state đầu tiên của processing. `processing_metrics.json` là replay anchor cho `silent_ratio`, không phải cache tạm.

Guard chặn bug: persist dùng temp file + `replace()` atomic ở `ProcessingRunMetrics.persist()`, nên state file không bị half-write dễ đọc nhầm.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_pipeline.py -q -k "silent_ratio_recovers_from_persisted_run_state_after_restart or replayed_segment_keeps_silent_ratio_stable_after_restart"
```

#### Micro-step 3.5.9. Update Welford RAM

```python
self._welford_state_by_run_id[payload.run_id] = next_welford_state
```

Tại sao viết vậy: đây là in-memory state (state RAM, chỉ tồn tại trong process, mất khi restart). Nó chỉ được phép đổi sau khi outputs đã publish xong và state file đã bền.

Guard chặn bug: nếu update RAM trước `feature_publish` hoặc trước `processing_metrics.json`, crash sẽ làm RAM của process cũ đi trước durability, sinh split-brain giữa những gì đã “tính trong đầu” và những gì restart có thể khôi phục.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_pipeline.py -q -k "welford_state_does_not_advance_when_feature_publish_fails"
```

#### Micro-step 3.5.10. Update run-metrics RAM

```python
self._run_metrics_by_run_id[payload.run_id] = next_run_metrics
```

Tại sao viết vậy: RAM copy phải đi sau state file vì RAM không cứu được restart.

Guard chặn bug: restart sau crash phải lấy lại `silent_ratio` từ `processing_metrics.json`, không được phụ thuộc vào dictionary trong memory.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_pipeline.py -q -k "silent_ratio_recovers_from_persisted_run_state_after_restart or replayed_segment_keeps_silent_ratio_stable_after_restart"
```

#### Micro-step 3.5.11. Commit Kafka offset ở `run()`, không commit trong `process_payload()`

```python
consumer.commit(message=record.message, asynchronous=False)
```

Tại sao viết vậy: offset commit phải là bước cuối cùng sau `publish outputs -> persist file -> update RAM`. Nếu commit sớm hơn, restart sẽ không replay record dù outputs/state chưa bền đủ.

Guard chặn bug: khi commit fail, code log rõ “published outputs but failed to commit the Kafka offset” và để record uncommitted để restart replay.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests\unit\test_processing_runtime.py -q -k "processing_run_commits_after_successful_outputs or offset_commit_fails"
```

Thứ tự toàn bộ orchestrator phải được giữ nguyên:

```text
Publish outputs
<
Persist state file
<
Update RAM
<
Commit offset
```

Nếu đảo `Update RAM` lên trước `Persist state file`, bạn tạo ra split-brain:

```text
RAM_old_process != Durable state_restart
```

Nếu đảo `Commit offset` lên trước tất cả, bạn đánh mất khả năng replay một logical segment khi crash xảy ra giữa đường.

---

### Trace 1. Happy Path

#### Node 1. Outputs vừa publish xong, state file chưa được ghi

- File/hàm đang chạy: `processing/pipeline.py::process_payload()` ngay sau `publish_audio_features_event()` và `_publish_success_metrics()`.
- Event đã publish xong: `audio.features` cho segment hiện tại, rồi `system.metrics` gồm `processing_ms` và `silent_ratio`.
- State file đã được ghi: chưa có; `processing_metrics.json` vẫn chưa được chạm tới ở node này.
- State RAM CHƯA được phép cập nhật tại thời điểm đó: `_welford_state_by_run_id[run_id]` và `_run_metrics_by_run_id[run_id]` chưa được phép swap sang `next_*`.
- Test hoặc lệnh verify nào chứng minh đúng đoạn trace đó: `test_processing_pipeline_emits_audio_features_from_claim_check_artifact`; `test_run_metrics_do_not_advance_when_metric_publish_fails`.

#### Node 2. `processing_metrics.json` vừa durable xong, RAM chưa swap

- File/hàm đang chạy: `processing/pipeline.py::_persist_run_metrics()` gọi xuống `processing/modules/metrics.py::persist()`.
- Event đã publish xong: vẫn là `audio.features`, `system.metrics.processing_ms`, `system.metrics.silent_ratio`; không có event mới ở node này.
- State file đã được ghi: `artifacts/runs/<run_id>/state/processing_metrics.json`, qua temp file rồi `replace()` atomic.
- State RAM CHƯA được phép cập nhật tại thời điểm đó: `WelfordState` RAM và `ProcessingRunMetrics` RAM vẫn chưa được phép mutate; restart phải đọc lại được từ file trước đã.
- Test hoặc lệnh verify nào chứng minh đúng đoạn trace đó: `test_silent_ratio_recovers_from_persisted_run_state_after_restart`; `test_replayed_segment_keeps_silent_ratio_stable_after_restart`.

#### Node 3. RAM vừa swap xong, offset chưa commit

- File/hàm đang chạy: cuối `processing/pipeline.py::process_payload()`.
- Event đã publish xong: `audio.features`, `processing_ms`, `silent_ratio` đều đã có delivery report.
- State file đã được ghi: `processing_metrics.json` đã durable cho `run_id` hiện tại.
- State RAM CHƯA được phép cập nhật tại thời điểm đó: không được mutate thêm lần hai vào `_welford_state_by_run_id` hay `_run_metrics_by_run_id`; business state đã chốt, chỉ còn quyền commit offset.
- Test hoặc lệnh verify nào chứng minh đúng đoạn trace đó: `test_processing_pipeline_emits_audio_features_from_claim_check_artifact`; `test_welford_updates_match_manual_per_bin_statistics`.

#### Node 4. Offset commit xong

- File/hàm đang chạy: `processing/pipeline.py::run()` tại `consumer.commit(message=record.message, asynchronous=False)`.
- Event đã publish xong: không có event mới; ba output của segment hiện tại đã xong từ các node trước.
- State file đã được ghi: `processing_metrics.json` đã tồn tại và writable/readable cho restart path.
- State RAM CHƯA được phép cập nhật tại thời điểm đó: mọi `WelfordState`/`ProcessingRunMetrics` RAM cho segment này đã đóng; commit offset không được kéo theo side-effect business nào nữa.
- Test hoặc lệnh verify nào chứng minh đúng đoạn trace đó: `test_processing_run_commits_after_successful_outputs`.

---

### Trace 2. Crash / Replay Path

#### Node 1. DSP xong nhưng chưa được phép cập nhật state

- File/hàm đang chạy: `processing/pipeline.py::process_payload()` ngay sau `summarize_rms()`, `compute()`, `is_silent_segment()`, `update_welford()`, `with_recorded_success()`.
- Event đã publish xong: chưa có event nào; `audio.features` còn chưa bắn.
- State file đã được ghi: chưa có; `processing_metrics.json` chưa được ghi.
- State RAM CHƯA được phép cập nhật tại thời điểm đó: `_welford_state_by_run_id` và `_run_metrics_by_run_id` phải giữ nguyên dù `next_welford_state` và `next_run_metrics` đã được tính xong.
- Test hoặc lệnh verify nào chứng minh đúng đoạn trace đó: `test_welford_state_does_not_advance_when_feature_publish_fails`; `test_run_metrics_do_not_advance_when_metric_publish_fails`.

#### Node 2. Publish fail và flow phải chết trước khi state advance

- File/hàm đang chạy: `processing/pipeline.py::publish_audio_features_event()` hoặc `processing/pipeline.py::_publish_success_metrics()`.
- Event đã publish xong: hoặc chưa có gì (`feature_publish_failed`), hoặc mới có `audio.features` nhưng `system.metrics` chưa đủ (`metric_publish_failed`).
- State file đã được ghi: chưa có; `processing_metrics.json` vẫn chưa được tạo/cập nhật.
- State RAM CHƯA được phép cập nhật tại thời điểm đó: `_welford_state_by_run_id` và `_run_metrics_by_run_id` vẫn phải giữ nguyên 100%.
- Test hoặc lệnh verify nào chứng minh đúng đoạn trace đó: `test_welford_state_does_not_advance_when_feature_publish_fails`; `test_run_metrics_do_not_advance_when_metric_publish_fails`.

#### Node 3. Split-brain sẽ xảy ra nếu ai đó cập nhật RAM trước durability

- File/hàm đang chạy: vẫn là `processing/pipeline.py::process_payload()`, nhưng đây là node phân tích ordering, không phải node mà current code cho phép commit.
- Event đã publish xong: có thể chưa có gì, hoặc có `audio.features` mà chưa có đủ metrics.
- State file đã được ghi: chưa có; `processing_metrics.json` vẫn chưa durable.
- State RAM CHƯA được phép cập nhật tại thời điểm đó: nếu ai đó lỡ update `_welford_state_by_run_id` hoặc `_run_metrics_by_run_id` ở đây, process cũ sẽ “nhớ” segment còn process mới sau restart thì không; đó chính là split-brain giữa RAM cũ và durable state.
- Test hoặc lệnh verify nào chứng minh đúng đoạn trace đó: current repo chứng minh **không** rơi vào node sai bằng `test_welford_state_does_not_advance_when_feature_publish_fails` và `test_run_metrics_do_not_advance_when_metric_publish_fails`.

#### Node 4. Outputs đã publish, state file đã ghi, nhưng offset commit fail

- File/hàm đang chạy: `processing/pipeline.py::run()` tại `consumer.commit(...)`.
- Event đã publish xong: `audio.features`, `processing_ms`, `silent_ratio` đều đã xong; current code còn tránh bắn thêm `feature_errors` ở path này.
- State file đã được ghi: `processing_metrics.json` đã durable xong trước khi chạy tới commit.
- State RAM CHƯA được phép cập nhật tại thời điểm đó: không được mutate lại Welford/run-metrics sau commit fail; record phải được để uncommitted để restart replay, không được “cứu cháy” bằng RAM.
- Test hoặc lệnh verify nào chứng minh đúng đoạn trace đó: `test_processing_run_does_not_emit_feature_errors_when_offset_commit_fails`.

#### Node 5. Restart / replay cùng `run_id`

- File/hàm đang chạy: `processing/pipeline.py::run_metrics_for()` gọi `processing/modules/metrics.py::from_state_file()`, rồi `process_payload()` xử lý lại segment.
- Event đã publish xong: replay sẽ publish lại theo đúng current flow; idempotency ở đây nằm ở persisted run metrics, tức là cùng logical segment không làm `silent_ratio` drift.
- State file đã được ghi: `processing_metrics.json` cũ được đọc lại trước, rồi ghi đè ổn định nếu segment là mới; nếu segment replay trùng, file vẫn giữ cardinality logic cũ.
- State RAM CHƯA được phép cập nhật tại thời điểm đó: trước khi file state được load xong, `_run_metrics_by_run_id` không được tự chế số liệu; `WelfordState` RAM vẫn là best-effort, không phải restart-safe snapshot ở repo hiện tại.
- Test hoặc lệnh verify nào chứng minh đúng đoạn trace đó: `test_silent_ratio_recovers_from_persisted_run_state_after_restart`; `test_replayed_segment_keeps_silent_ratio_stable_after_restart`.

Dừng ở đây. CHUNK 3 kết thúc tại processing pipeline.

---

**Phase 4 — Xây Dựng Writer và Persistence Semantics**

### Bước 4.1. Mở `writer/modules/consumer.py` rồi nhảy ngay sang `writer/pipeline.py::_persist_record()`: validate envelope trước khi transaction tồn tại

`consumer.py` chỉ nên làm một việc: kéo record từ Kafka về `ConsumedRecord`. Guard thật cho writer nằm ở `pipeline.py::_persist_record()`, và nó phải đứng **trước** bất kỳ transaction nào:

```text
BEGIN <=> schema_ok(envelope) and schema_ok(payload)
```

Trong code, `BEGIN` không xuất hiện dưới dạng chuỗi SQL literal; nó được materialize bởi `transaction_cursor()` hoặc `pooled_transaction_cursor()` vì connection chạy với `autocommit=False`. Vì vậy, mọi thứ đứng trước `with cursor_context as (_, cursor):` chính là vùng tiền-transaction.

```python
def _persist_record(
    self,
    record: ConsumedRecord,
    *,
    pool: ConnectionPool | None = None,
    raw_envelope: dict[str, object] | None = None,
    write_started_at: float | None = None,
) -> WriterPersistenceOutcome:
    envelope = raw_envelope if raw_envelope is not None else deserialize_envelope(record.value)
    started_at = perf_counter() if write_started_at is None else write_started_at
    try:
        payload = validate_envelope_dict(envelope, expected_event_type=record.topic)
    except ValueError as exc:
        raise WriterStageError(
            "envelope_invalid",
            "Writer failed while validating the current envelope.",
        ) from exc

    context = self._extract_record_context(envelope)
    try:
        payload_model = coerce_payload_model(record.topic, payload)
    except WriterPayloadValidationError as exc:
        raise WriterStageError(
            "envelope_invalid",
            "Writer failed while validating the current payload.",
        ) from exc

    if pool is None:
        cursor_context = transaction_cursor(self.settings.database)
    else:
        cursor_context = pooled_transaction_cursor(pool)
```

Tại sao viết vậy: record lỗi schema không được phép chạm vào DB pool. Nếu bạn mở transaction trước rồi mới validate, mỗi junk envelope sẽ:

- chiếm một connection trong pool,
- mở một transaction vô nghĩa rồi rollback,
- làm record hợp lệ đứng hàng chờ phía sau đống input không bao giờ đáng được vào DB.

Đó là đúng nghĩa “rác DB connection”: connection bị bận vì dữ liệu mà lẽ ra phải chết ngay ở CPU path, không phải ở I/O path.

Guard chặn bug nằm ở hai lớp:

- `validate_envelope_dict(...)` chặn envelope lệch `event_type`, thiếu field top-level, hoặc `payload.run_id` vênh với `envelope.run_id`.
- `coerce_payload_model(...)` chặn payload drift theo topic, ví dụ `audio.features` thiếu `processing_ms`.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_writer_pipeline.py -q -k "persist_record_accepts_canonical_v1_envelope or persist_record_rejects_top_level_payload_run_id_mismatch or persist_record_rejects_payload_schema_drift"
```

### Bước 4.2. Mở `writer/modules/upsert_metadata.py`: logical key và physical key trùng nhau, nên `ON CONFLICT` là đúng đòn

Metadata là case dễ nhất vì khóa logic và khóa vật lý của bảng trùng nhau:

```text
K_meta = (run_id, track_id)
```

```text
R' = (R - rows with K_meta = k) union {r_k^new}
```

Đọc LaTeX này xong thì nhìn ngay SQL sẽ thấy nó chính là `replace-by-key`:

```sql
INSERT INTO track_metadata (
    run_id,
    track_id,
    artist_id,
    genre,
    subset,
    source_audio_uri,
    validation_status,
    duration_s,
    manifest_uri,
    checksum
)
VALUES (
    %(run_id)s,
    %(track_id)s,
    %(artist_id)s,
    %(genre)s,
    %(subset)s,
    %(source_audio_uri)s,
    %(validation_status)s,
    %(duration_s)s,
    %(manifest_uri)s,
    %(checksum)s
)
ON CONFLICT (run_id, track_id) DO UPDATE SET
    artist_id = EXCLUDED.artist_id,
    genre = EXCLUDED.genre,
    subset = EXCLUDED.subset,
    source_audio_uri = EXCLUDED.source_audio_uri,
    validation_status = EXCLUDED.validation_status,
    duration_s = EXCLUDED.duration_s,
    manifest_uri = EXCLUDED.manifest_uri,
    checksum = EXCLUDED.checksum;
```

Block Python tương ứng gần như không có trò ảo thuật:

```python
def persist_track_metadata(cursor: Cursor, payload: AudioMetadataPayload) -> int:
    cursor.execute(TRACK_METADATA_UPSERT, asdict(payload))
    return cursor.rowcount
```

Tại sao viết vậy: replay của `audio.metadata` không cần “insert mới theo thời gian”; nó cần hội tụ về một hàng logic duy nhất cho mỗi `(run_id, track_id)`. Vì vậy `ON CONFLICT (run_id, track_id)` là semantic match hoàn hảo với primary key của bảng `track_metadata`.

Guard chặn bug ở đây là danh sách cột trong `DO UPDATE SET` phải đầy đủ. Nếu bạn quên `duration_s`, `manifest_uri`, hay `checksum`, replay sẽ giữ lại dữ liệu cũ một cách im lặng dù event mới đã đúng hơn. PoC này không cần partial merge thông minh; nó cần deterministic overwrite.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_writer_persistence.py -q -k "track_metadata_persists_duration_s"
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/integration/test_writer_schema_contract.py -q -k "track_metadata_is_regular_table"
```

### Bước 4.3. Mở `writer/modules/upsert_features.py`: khóa logic không trùng physical PK của TimescaleDB, nên phải `UPDATE` trước rồi mới `INSERT`

Đây là hot path dễ làm hỏng replay nhất. Bắt đầu từ schema thật trong `infra/sql/002_core_tables.sql`:

```sql
CREATE TABLE IF NOT EXISTS audio_features (
    ts TIMESTAMPTZ NOT NULL,
    run_id TEXT NOT NULL,
    track_id BIGINT NOT NULL,
    segment_idx INTEGER NOT NULL,
    artifact_uri TEXT NOT NULL,
    checksum TEXT NOT NULL,
    manifest_uri TEXT,
    rms DOUBLE PRECISION NOT NULL,
    silent_flag BOOLEAN NOT NULL,
    mel_bins INTEGER NOT NULL,
    mel_frames INTEGER NOT NULL,
    processing_ms DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ts, run_id, track_id, segment_idx)
);

CREATE INDEX IF NOT EXISTS idx_audio_features_lookup
ON audio_features (run_id, track_id, segment_idx);
```

Khóa logic mà hệ thống audio thật sự quan tâm là:

```text
K_feat^logical = (run_id, track_id, segment_idx)
```

Nhưng khóa vật lý mà TimescaleDB buộc phải có trên hypertable là:

```text
K_feat^physical = (ts, run_id, track_id, segment_idx)
```

```text
K_feat^logical != K_feat^physical
```

Nếu bạn viết ngây thơ:

```sql
INSERT INTO audio_features (...)
VALUES (...)
ON CONFLICT (ts, run_id, track_id, segment_idx) DO UPDATE ...
```

thì replay cùng segment nhưng khác `ts` sẽ **không conflict**. Database thấy hai hàng hợp lệ về physical PK, còn business semantics thì nổ row rác. Vì vậy current code không dùng `ON CONFLICT` chay ở đây. Nó đi theo chiến lược `lock -> update-by-logical-key -> insert-if-missing`.

Block core phải gõ theo đúng thứ tự này:

```python
def persist_audio_features(cursor: Cursor, payload: AudioFeaturesPayload) -> int:
    params = asdict(payload)
    acquire_transaction_advisory_lock(
        cursor,
        payload.run_id,
        payload.track_id,
        payload.segment_idx,
    )
    cursor.execute(AUDIO_FEATURES_UPSERT, params)
    matches = cursor.fetchall()
    if len(matches) > 1:
        raise AudioFeaturesNaturalKeyError(
            "audio_features natural key lookup matched multiple rows for "
            f"({payload.run_id}, {payload.track_id}, {payload.segment_idx})."
        )
    if len(matches) == 1:
        return 1

    cursor.execute(AUDIO_FEATURES_INSERT, params)
    return cursor.rowcount
```

SQL thật của khối `UPDATE` và `INSERT` là:

```sql
UPDATE audio_features
SET
    artifact_uri = %(artifact_uri)s,
    checksum = %(checksum)s,
    manifest_uri = %(manifest_uri)s,
    rms = %(rms)s,
    silent_flag = %(silent_flag)s,
    mel_bins = %(mel_bins)s,
    mel_frames = %(mel_frames)s,
    processing_ms = %(processing_ms)s
WHERE run_id = %(run_id)s
  AND track_id = %(track_id)s
  AND segment_idx = %(segment_idx)s
RETURNING 1;
```

```sql
INSERT INTO audio_features (
    ts,
    run_id,
    track_id,
    segment_idx,
    artifact_uri,
    checksum,
    manifest_uri,
    rms,
    silent_flag,
    mel_bins,
    mel_frames,
    processing_ms
)
VALUES (
    %(ts)s,
    %(run_id)s,
    %(track_id)s,
    %(segment_idx)s,
    %(artifact_uri)s,
    %(checksum)s,
    %(manifest_uri)s,
    %(rms)s,
    %(silent_flag)s,
    %(mel_bins)s,
    %(mel_frames)s,
    %(processing_ms)s
);
```

Tại sao phải có `pg_advisory_xact_lock(...)`: repo giữ transaction isolation (mức cô lập transaction) ở mức mặc định của PostgreSQL/psycopg, không cố nâng cả service lên `SERIALIZABLE`. Thay vào đó, nó lấy advisory lock (khóa tư vấn do application tự xin và tự định nghĩa key) theo đúng logical key của segment. Cách này serialize đúng `(run_id, track_id, segment_idx)` mà không ép mọi transaction khác phải trả giá.

Guard chặn bug có ba lớp:

- `acquire_transaction_advisory_lock(...)` chặn hai replay song song cùng nhìn thấy “chưa có row” rồi cùng `INSERT`.
- `if len(matches) > 1` nổ `AudioFeaturesNaturalKeyError` ngay khi bảng đã drift thành nhiều row cho cùng logical key.
- `manifest_uri` được phép `NULL`; guard này ngăn writer ép claim-check manifest thành hard dependency ở những test path chỉ có artifact tối thiểu.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_writer_persistence.py -q -k "audio_features_inserts_when_natural_key_is_missing or audio_features_updates_when_natural_key_exists or audio_features_fails_when_natural_key_matches_multiple_rows or audio_features_allows_missing_manifest_uri"
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/integration/test_writer_schema_contract.py -q -k "audio_features_mentions_logical_key_columns"
```

### Bước 4.4. Mở `writer/modules/write_metrics.py` và `writer/modules/metrics.py`: snapshot replay-safe khác hẳn append-only metrics

Ở `system_metrics`, không phải metric nào cũng được quyền dedupe. Current code tách rõ hai class:

- Snapshot replay-safe: metric đại diện cho **trạng thái logic hiện tại**, ví dụ `scope=run_total` hoặc `scope=writer_record`.
- Append-only: metric đại diện cho **một sample lịch sử**, ví dụ `processing_ms` theo từng event; row mới là row mới, không collapse vào row cũ.

Toán học của hai class này khác hẳn nhau:

```text
K_metric = (run_id, service_name, metric_name, labels_json)
```

Với snapshot replay-safe:

```text
M' = (M - rows with K_metric = k) union {m_k^new}
```

Với append-only:

```text
M' = M union {m^new}
```

Code branch đúng là:

```python
REPLAY_SAFE_METRIC_SCOPES = {"run_total", "writer_record"}

def persist_system_metrics(cursor: Cursor, payload: SystemMetricsPayload) -> int:
    params = asdict(payload)
    params["labels_json"] = Jsonb(payload.labels_json)
    if payload.labels_json.get("scope") not in REPLAY_SAFE_METRIC_SCOPES:
        cursor.execute(SYSTEM_METRICS_INSERT, params)
        return cursor.rowcount

    logical_key = json.dumps(payload.labels_json, separators=(",", ":"), sort_keys=True)
    acquire_transaction_advisory_lock(
        cursor,
        payload.run_id,
        payload.service_name,
        payload.metric_name,
        logical_key,
    )
    cursor.execute(SYSTEM_METRICS_REPLAY_SAFE_SELECT, params)
    matches = cursor.fetchall()
    if len(matches) >= 1:
        params["survivor_tableoid"] = matches[0][0]
        params["survivor_ctid"] = matches[0][1]
        if len(matches) > 1:
            cursor.execute(SYSTEM_METRICS_REPLAY_SAFE_DELETE_DUPLICATES, params)
        cursor.execute(SYSTEM_METRICS_REPLAY_SAFE_DELETE_SURVIVOR, params)
        cursor.execute(SYSTEM_METRICS_INSERT, params)
        return cursor.rowcount

    cursor.execute(SYSTEM_METRICS_INSERT, params)
    return cursor.rowcount
```

SQL thật cho nhánh replay-safe là:

```sql
SELECT
    tableoid::oid,
    ctid::text
FROM system_metrics
WHERE run_id = %(run_id)s
  AND service_name = %(service_name)s
  AND metric_name = %(metric_name)s
  AND labels_json = %(labels_json)s
ORDER BY ts DESC, tableoid::oid DESC, ctid DESC;
```

```sql
DELETE FROM system_metrics
WHERE run_id = %(run_id)s
  AND service_name = %(service_name)s
  AND metric_name = %(metric_name)s
  AND labels_json = %(labels_json)s
  AND NOT (
      tableoid = %(survivor_tableoid)s::oid
      AND ctid = %(survivor_ctid)s::tid
  );
```

```sql
DELETE FROM system_metrics
WHERE tableoid = %(survivor_tableoid)s::oid
  AND ctid = %(survivor_ctid)s::tid;
```

```sql
INSERT INTO system_metrics (
    ts,
    run_id,
    service_name,
    metric_name,
    metric_value,
    labels_json,
    unit
)
VALUES (
    %(ts)s,
    %(run_id)s,
    %(service_name)s,
    %(metric_name)s,
    %(metric_value)s,
    %(labels_json)s,
    %(unit)s
);
```

Tại sao phải dùng `tableoid + ctid`: `CTID` (địa chỉ vật lý row version trong PostgreSQL) chỉ unique trong một physical relation. `tableoid` là OID của bảng hoặc chunk đang chứa row đó. Vì `system_metrics` là hypertable, duplicate logical rows có thể nằm ở các chunk khác nhau; chỉ dùng `ctid` một mình là không đủ để xóa đúng row.

Writer nội bộ dùng replay-safe snapshot bằng cách khóa `labels_json` ngay từ lúc build payload:

```python
def build_writer_metric_payload(...) -> SystemMetricsPayload:
    return SystemMetricsPayload(
        ts=_utc_now_iso(),
        run_id=run_id,
        service_name="writer",
        metric_name=metric_name,
        metric_value=metric_value,
        labels_json=WriterMetricLabelSet(
            topic=topic,
            status=status,
            partition=partition,
            offset=offset,
            failure_class=failure_class,
        ).to_dict(),
        unit=unit,
    )
```

Tại sao `write_ms` và `rows_upserted` phải ghi thẳng DB chứ không bắn ngược Kafka: writer đang consume `WRITER_INPUT_TOPICS = (audio.metadata, audio.features, system.metrics)`. Nếu chính writer publish thêm `system.metrics` của mình lên Kafka, nó sẽ tự ăn lại metric của chính nó và sinh vòng lặp khuếch đại. Hơn nữa, hai metric này phải phản ánh **đúng transaction vừa commit**, nên nó phải nằm trong cùng DB transaction thay vì trở thành một event phụ với ordering riêng.

Guard chặn bug:

- `scope` quyết định semantics; chỉ `run_total` và `writer_record` mới được phép rewrite.
- `logical_key = json.dumps(..., sort_keys=True)` khóa labels JSON về canonical form trước khi băm advisory lock key.
- Duplicate đã lỡ tồn tại vì replay cũ được quét sạch bằng `DELETE_DUPLICATES`, rồi row survivor cũng bị xóa để `INSERT` row mới với `ts` mới nhất.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_writer_persistence.py -q -k "system_metrics_persists_unit or run_total_system_metrics_rewrites_existing_logical_row or run_total_system_metrics_inserts_when_logical_row_is_missing or run_total_system_metrics_repairs_duplicate_logical_rows or writer_record_system_metrics_rewrites_existing_logical_row or writer_internal_metric_payload_uses_locked_labels_and_unit"
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_writer_smoke_verify.py -q -k "assert_writer_snapshot_accepts_happy_path or assert_writer_snapshot_fails_on_wrong_writer_record_count or assert_writer_snapshot_fails_on_writer_metric_contract_drift"
```

### Bước 4.5. Mở `writer/modules/checkpoint_store.py`, `writer/modules/offset_manager.py`, rồi khóa vi phẫu `_persist_record()`

Checkpoint phải nằm trong cùng transaction với payload. Nếu payload đã vào DB mà checkpoint chưa vào, restart sẽ replay record hợp lệ; đó là chấp nhận được vì sink phải idempotent. Nhưng nếu checkpoint vào trước payload, restart sẽ tưởng offset đó đã bền vững và bỏ qua record dù payload chưa từng tồn tại. Đó là data loss thật.

SQL checkpoint thật là:

```sql
INSERT INTO run_checkpoints (
    consumer_group,
    topic_name,
    partition_id,
    run_id,
    last_committed_offset
)
VALUES (
    %(consumer_group)s,
    %(topic_name)s,
    %(partition_id)s,
    %(run_id)s,
    %(last_committed_offset)s
)
ON CONFLICT (consumer_group, topic_name, partition_id) DO UPDATE SET
    run_id = EXCLUDED.run_id,
    last_committed_offset = EXCLUDED.last_committed_offset,
    updated_at = NOW();
```

Điều kiện sống còn cho offset commit được mã hóa thành một công thức nhị phân rất thẳng:

```text
commit_allowed <=> (rows_written > 0) and (checkpoint_rows > 0)
```

Block code thật:

```python
def build_commit_decision(rows_written: int, checkpoints_ready: bool) -> OffsetCommitDecision:
    if not checkpoints_ready:
        return OffsetCommitDecision(
            commit_allowed=False,
            reason="checkpoint update not complete",
            failure_class="checkpoint_failed",
        )
    if rows_written <= 0:
        return OffsetCommitDecision(
            commit_allowed=False,
            reason="invalid persistence result",
            failure_class="invalid_persistence_result",
        )
    return OffsetCommitDecision(
        commit_allowed=True,
        reason="persistence and checkpoints complete",
    )
```

Bây giờ tách `_persist_record()` thành micro-step đúng như runtime:

#### Micro-step 4.5.1. Mở transaction boundary

```python
if pool is None:
    cursor_context = transaction_cursor(self.settings.database)
else:
    cursor_context = pooled_transaction_cursor(pool)

with cursor_context as (_, cursor):
```

Tại sao viết vậy: `pooled_transaction_cursor()` và `transaction_cursor()` là runtime equivalent của `BEGIN`. Chúng gom toàn bộ payload, checkpoint, và internal metrics vào cùng một commit unit.

Guard chặn bug: helper ở `shared/db.py` rollback mọi exception trước khi re-raise, nên không có chuyện payload ghi dở mà cursor thoát “êm”.

```python
@contextmanager
def pooled_transaction_cursor(pool: ConnectionPool) -> Iterator[tuple[Connection, Cursor]]:
    with pool.connection() as connection:
        with connection.cursor() as cursor:
            try:
                yield connection, cursor
            except Exception:
                connection.rollback()
                raise
            connection.commit()
```

#### Micro-step 4.5.2. Persist payload trước

```python
rows_written = persist_envelope_payload(
    cursor=cursor,
    topic=record.topic,
    payload=payload_model,
)
```

Tại sao viết vậy: payload là business fact chính. Không có payload thì checkpoint chẳng có gì để checkpoint cả.

Guard chặn bug: `rows_written` bị giữ lại để micro-step commit decision kiểm tra. Giá trị `0` không được xem là “không sao”.

#### Micro-step 4.5.3. Persist checkpoint sau payload, nhưng vẫn trong cùng transaction

```python
checkpoint_record = build_checkpoint_record(
    consumer_group=self.settings.consumer_group,
    topic_name=record.topic,
    partition_id=record.partition,
    run_id=str(envelope["run_id"]),
    last_committed_offset=record.offset,
)
checkpoint_rows = persist_checkpoint(cursor, checkpoint_record)
```

Tại sao viết vậy: checkpoint phải phản ánh “payload này đã được ghi trong chính transaction hiện tại”, không phải “payload này dự kiến sẽ được ghi”.

Guard chặn bug: checkpoint viết bằng cùng `cursor`, nên nếu commit cuối transaction fail thì payload và checkpoint cùng rollback; không có split state giữa hai bảng.

#### Micro-step 4.5.4. Tính commit decision ngay tại chỗ

```python
decision = build_commit_decision(
    rows_written=rows_written,
    checkpoints_ready=checkpoint_rows > 0,
)
if not decision.commit_allowed:
    raise WriterStageError(
        decision.failure_class or "invalid_persistence_result",
        decision.reason,
    )
```

Tại sao viết vậy: đây là điểm chặn cuối trước khi transaction được quyền đi tới `COMMIT`. Điều kiện được encode thành boolean tối thiểu, không mở cửa cho diễn giải mơ hồ.

Guard chặn bug: `checkpoint_rows = 0` hoặc `rows_written <= 0` đều nổ exception ngay trong transaction, ép helper ở `shared/db.py` rollback toàn bộ. Không có đường lén nào cho offset tiến lên khi persistence chưa hoàn tất.

#### Micro-step 4.5.5. Persist system metrics nội bộ ngay trong transaction

```python
write_elapsed_ms = (perf_counter() - started_at) * 1000.0
run_id = context.run_id or str(envelope["run_id"])
persist_system_metrics(
    cursor,
    build_writer_metric_payload(
        run_id=run_id,
        topic=record.topic,
        metric_name="write_ms",
        metric_value=write_elapsed_ms,
        unit="ms",
        status="ok",
        partition=record.partition,
        offset=record.offset,
    ),
)
persist_system_metrics(
    cursor,
    build_writer_metric_payload(
        run_id=run_id,
        topic=record.topic,
        metric_name="rows_upserted",
        metric_value=float(rows_written),
        unit="count",
        status="ok",
        partition=record.partition,
        offset=record.offset,
    ),
)
```

Tại sao ghi thẳng DB thay vì bắn ngược Kafka:

- writer tự consume `system.metrics`, nên publish ngược sẽ tự sinh vòng lặp.
- `write_ms` và `rows_upserted` là internal sink facts, không phải cross-service contract.
- metric này phải bám vào cùng transaction với payload; nếu payload rollback thì metric cũng phải biến mất theo.

Guard chặn bug: labels của `writer_record` khóa luôn `topic`, `status`, `partition`, `offset`, nên replay cùng record sẽ rewrite cùng logical row thay vì phình số lượng snapshot metric.

#### Micro-step 4.5.6. Đóng transaction bằng `COMMIT`

Ở current repo, `COMMIT` xảy ra khi thoát `with cursor_context ...` mà không có exception. Thứ tự thật là:

```sql
BEGIN;
-- Persist Payload
-- Persist Checkpoint
-- Persist Internal Metrics
COMMIT;
```

Tại sao viết vậy: `COMMIT` phải đứng sau tất cả DB side effects. Nếu chưa commit mà đã báo Kafka “xong rồi”, broker sẽ không replay nữa dù DB có thể chưa durable.

Guard chặn bug: mọi exception trước điểm này đi vào `rollback()` của helper; transaction đóng với trạng thái sạch.

#### Micro-step 4.5.7. `consumer.commit()` là bước cuối cùng và nằm ngoài DB transaction

```python
try:
    consumer.commit(message=record.message, asynchronous=False)
except Exception as exc:
    raise WriterStageError(
        "offset_commit_failed",
        "Writer persisted the current record but failed to commit the Kafka offset.",
    ) from exc
```

`offset commit` (xác nhận với Kafka rằng consumer đã xử lý bền vững record đến offset này và broker không cần giao lại trong luồng bình thường) phải là bước cuối cùng. Nếu bạn gọi nó trước `COMMIT`, bạn mua đúng kiểu data loss khó debug nhất: Kafka tin record đã xong, còn DB thì chưa bao giờ durable.

Lệnh verify cho toàn bộ ordering:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_writer_pipeline.py -q -k "successful_record_is_committed_once or commit_failure_emits_failure_metric_and_stops_before_next_record or persist_record_rejects_invalid_checkpoint_result_before_commit"
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_offset_manager.py -q
```

---

### Trace 1. Happy Path Persistence

#### Node 1. Record vừa qua schema gate, transaction chưa được phép tồn tại

- File/hàm nào đang chạy: `writer/pipeline.py::_persist_record()` tại `validate_envelope_dict(...)` và `coerce_payload_model(...)`.
- Trạng thái Transaction: Chưa mở.
- DB state: Chưa có gì flush xuống đĩa; chưa có cursor transactional nào được mượn.
- Trạng thái Offset Kafka: Chưa commit.
- Test hoặc lệnh verify nào chứng minh: `test_persist_record_accepts_canonical_v1_envelope`, `test_persist_record_rejects_payload_schema_drift`, `test_persist_record_rejects_top_level_payload_run_id_mismatch`.

#### Node 2. Payload và checkpoint đã được ghi vào cùng transaction

- File/hàm nào đang chạy: `writer/pipeline.py::_persist_record()` sau `persist_envelope_payload(...)` và `persist_checkpoint(...)`.
- Trạng thái Transaction: Đang mở.
- DB state: Chưa flush xuống durable state; row mới chỉ tồn tại trong transaction hiện tại và còn có thể rollback.
- Trạng thái Offset Kafka: Chưa commit.
- Test hoặc lệnh verify nào chứng minh: `test_track_metadata_persists_duration_s`, `test_audio_features_inserts_when_natural_key_is_missing`, `test_commit_allowed_after_persistence_and_checkpoint`.

#### Node 3. Commit decision đã pass, internal writer metrics đã nằm trong cùng transaction

- File/hàm nào đang chạy: `writer/pipeline.py::_persist_record()` tại `build_commit_decision(...)` rồi `persist_system_metrics(...)` cho `write_ms` và `rows_upserted`.
- Trạng thái Transaction: Đang mở.
- DB state: Vẫn chưa flush durable; payload, checkpoint, và internal metrics còn buộc vào fate chung của transaction.
- Trạng thái Offset Kafka: Chưa commit.
- Test hoặc lệnh verify nào chứng minh: `test_run_total_system_metrics_rewrites_existing_logical_row`, `test_writer_record_system_metrics_rewrites_existing_logical_row`, `test_writer_internal_metric_payload_uses_locked_labels_and_unit`.

#### Node 4. DB transaction vừa `COMMIT`, nhưng Kafka offset vẫn chưa được đụng tới

- File/hàm nào đang chạy: `writer/pipeline.py::_persist_record()` vừa thoát `with cursor_context ...`; commit thật được gọi trong `shared/db.py`.
- Trạng thái Transaction: Đã Commit.
- DB state: Đã flush theo transaction boundary của PostgreSQL/TimescaleDB; payload, checkpoint, và internal metrics đã trở thành durable state.
- Trạng thái Offset Kafka: Chưa commit.
- Test hoặc lệnh verify nào chứng minh: `test_persist_record_accepts_canonical_v1_envelope`, `test_persist_record_rejects_invalid_checkpoint_result_before_commit`.

#### Node 5. Offset Kafka được commit sau cùng

- File/hàm nào đang chạy: `writer/pipeline.py::run()` tại `consumer.commit(message=record.message, asynchronous=False)`.
- Trạng thái Transaction: Đã Commit.
- DB state: Đã flush; không còn DB side effect nào treo lại.
- Trạng thái Offset Kafka: Đã commit.
- Test hoặc lệnh verify nào chứng minh: `test_successful_record_is_committed_once`.

---

### Trace 2. Idempotent Replay Path

#### Node 1. Replay mở transaction và lấy đúng advisory lock theo logical key

- File/hàm nào đang chạy: `writer/modules/upsert_features.py::persist_audio_features()` tại `acquire_transaction_advisory_lock(cursor, payload.run_id, payload.track_id, payload.segment_idx)`.
- Trạng thái Transaction: Đang mở.
- DB state: Chưa flush; transaction đang giữ quyền serialize cho đúng một logical segment.
- Trạng thái Offset Kafka: Chưa commit.
- Test hoặc lệnh verify nào chứng minh: `test_audio_features_inserts_when_natural_key_is_missing`, `test_audio_features_updates_when_natural_key_exists`.

#### Node 2. `UPDATE` thấy row cũ đã tồn tại và chặn nhánh `INSERT`

- File/hàm nào đang chạy: `writer/modules/upsert_features.py::persist_audio_features()` ngay sau `cursor.execute(AUDIO_FEATURES_UPSERT, params)`.
- Trạng thái Transaction: Đang mở.
- DB state: Chưa flush; logical row count của `(run_id, track_id, segment_idx)` vẫn không tăng, chỉ payload của row hiện có được thay mới trong transaction.
- Trạng thái Offset Kafka: Chưa commit.
- Test hoặc lệnh verify nào chứng minh: `test_audio_features_updates_when_natural_key_exists`.

#### Node 3. Nếu lookup ra nhiều hơn một row, transaction bị buộc phải chết

- File/hàm nào đang chạy: `writer/modules/upsert_features.py::persist_audio_features()` tại guard `if len(matches) > 1: raise AudioFeaturesNaturalKeyError(...)`.
- Trạng thái Transaction: Đang mở, nhưng sẽ bị rollback khi exception bubble lên helper transaction.
- DB state: Chưa flush; đây là điểm chặn để DB không đẻ thêm row rác lên trên một bảng đã drift.
- Trạng thái Offset Kafka: Chưa commit.
- Test hoặc lệnh verify nào chứng minh: `test_audio_features_fails_when_natural_key_matches_multiple_rows`.

#### Node 4. Replay hợp lệ cập nhật checkpoint rồi `COMMIT` mà không sinh row feature mới

- File/hàm nào đang chạy: `writer/pipeline.py::_persist_record()` sau `persist_checkpoint(...)`, rồi thoát transaction context.
- Trạng thái Transaction: Đã Commit.
- DB state: Đã flush; feature row logic vẫn là một hàng cho đúng `(run_id, track_id, segment_idx)`, checkpoint đã trỏ tới offset mới.
- Trạng thái Offset Kafka: Chưa commit.
- Test hoặc lệnh verify nào chứng minh: `test_commit_allowed_after_persistence_and_checkpoint`, `test_audio_features_updates_when_natural_key_exists`.

#### Node 5. Offset commit xong, DB không đẻ thêm row rác

- File/hàm nào đang chạy: `writer/pipeline.py::run()` tại `consumer.commit(...)`.
- Trạng thái Transaction: Đã Commit.
- DB state: Đã flush; replay hội tụ về cùng logical state thay vì phình row count.
- Trạng thái Offset Kafka: Đã commit.
- Test hoặc lệnh verify nào chứng minh: `test_assert_writer_snapshot_accepts_happy_path` và `test_assert_writer_snapshot_fails_on_wrong_writer_record_count`.

---

### Trace 3. Mini Failure Path

Trace này dùng nhánh `consumer.commit()` fail, vì đây là failure sắc nhất: DB đã durable nhưng Kafka offset vẫn phải cố ý giữ ở trạng thái uncommitted. Nhánh `checkpoint_rows = 0` đã bị chặn sớm hơn ở micro-step 4.5.4 bởi `test_persist_record_rejects_invalid_checkpoint_result_before_commit`.

#### Node 1. Payload, checkpoint, và internal metrics đều đã được ghi trong transaction

- File/hàm nào đang chạy: `writer/pipeline.py::_persist_record()` ở cuối transaction body.
- Trạng thái Transaction: Đang mở.
- DB state: Chưa flush durable; mọi row vẫn còn khả năng rollback nếu exception xuất hiện trước khi thoát context.
- Trạng thái Offset Kafka: Chưa commit.
- Test hoặc lệnh verify nào chứng minh: `test_persist_record_accepts_canonical_v1_envelope`.

#### Node 2. Transaction đã `COMMIT`, nên DB side đã an toàn

- File/hàm nào đang chạy: `writer/pipeline.py::_persist_record()` vừa return về `WriterPersistenceOutcome`.
- Trạng thái Transaction: Đã Commit.
- DB state: Đã flush theo boundary commit; payload, checkpoint, `write_ms`, và `rows_upserted` đều là durable state.
- Trạng thái Offset Kafka: Chưa commit.
- Test hoặc lệnh verify nào chứng minh: `test_persist_record_accepts_canonical_v1_envelope`, `test_commit_allowed_after_persistence_and_checkpoint`.

#### Node 3. `consumer.commit()` nổ lỗi, nên offset phải đứng yên

- File/hàm nào đang chạy: `writer/pipeline.py::run()` tại block `consumer.commit(...)` và nhánh `except` ném `WriterStageError("offset_commit_failed", ...)`.
- Trạng thái Transaction: Đã Commit; không còn DB transaction business nào mở để rollback nữa.
- DB state: Đã flush; đây chính là lý do không được “vớt vát” bằng cách coi record như đã ack Kafka.
- Trạng thái Offset Kafka: Chưa commit.
- Test hoặc lệnh verify nào chứng minh: `test_commit_failure_emits_failure_metric_and_stops_before_next_record`.

#### Node 4. Process dừng, record cố ý bị giữ ở trạng thái Kafka-uncommitted để hệ thống tự replay

- File/hàm nào đang chạy: `writer/pipeline.py::run()` trong nhánh error sau `classify_writer_failure(...)` và `_emit_failure_metric(...)`.
- Trạng thái Transaction: Không còn transaction business đang mở; transaction failure-metric riêng có thể mở/đóng độc lập.
- DB state: Payload gốc vẫn đã flush; failure metric, nếu ghi được, chỉ là phụ lục chẩn đoán.
- Trạng thái Offset Kafka: Chưa commit.
- Test hoặc lệnh verify nào chứng minh: `test_failed_record_is_left_uncommitted_and_exits`, `test_commit_failure_emits_failure_metric_and_stops_before_next_record`.

#### Node 5. Lần chạy sau replay cùng record và hội tụ nhờ idempotent sink

- File/hàm nào đang chạy: vòng `writer/pipeline.py::run()` mới, rồi `writer/modules/upsert_features.py::persist_audio_features()` hoặc `writer/modules/upsert_metadata.py::persist_track_metadata()` tùy topic.
- Trạng thái Transaction: Chưa mở ở đầu poll mới, rồi mở lại transaction mới cho replay.
- DB state: Bản ghi cũ đã flush sẵn, nên replay sẽ đi vào nhánh `UPDATE` hoặc `ON CONFLICT` thay vì tạo bản sao logic mới.
- Trạng thái Offset Kafka: Chưa commit ở đầu replay; chỉ được commit lại sau khi transaction replay mới thành công.
- Test hoặc lệnh verify nào chứng minh: `test_audio_features_updates_when_natural_key_exists`, `test_successful_record_is_committed_once`.

Dừng ở đây. CHUNK 4 kết thúc tại writer và persistence semantics.

---

**Phase 5 — Xây Dựng DB Views và Dashboard**

### Bước 5.1. Mở `infra/sql/003_operational_views.sql`: bóc `labels_json` thành surface SQL ổn định trước khi Grafana đụng tới nó

Nếu bạn để mỗi panel Grafana tự đào `labels_json` bằng `->>` và tự cast kiểu tại chỗ, bạn vừa copy cùng một luật parse vào hàng chục `rawSql` string khác nhau, vừa tạo điểm drift âm thầm giữa dashboard `A` và dashboard `B`. Đó là thảm họa kiến trúc vì contract dashboard bị phân mảnh theo panel JSON, không còn nằm trong SQL layer có thể version/diff/test được.

Block phải gõ trước là view normalize metric events:

```sql
CREATE OR REPLACE VIEW vw_dashboard_metric_events AS
SELECT
    ts,
    run_id,
    service_name,
    metric_name,
    metric_value,
    COALESCE(labels_json ->> 'scope', 'event') AS metric_scope,
    COALESCE(
        labels_json ->> 'status',
        CASE
            WHEN metric_name IN ('feature_errors', 'write_failures') THEN 'error'
            ELSE 'ok'
        END
    ) AS metric_status,
    labels_json ->> 'topic' AS topic_name,
    labels_json ->> 'failure_class' AS failure_class,
    CASE
        WHEN jsonb_typeof(labels_json -> 'partition') = 'number'
            THEN (labels_json ->> 'partition')::INTEGER
        ELSE NULL
    END AS kafka_partition,
    CASE
        WHEN jsonb_typeof(labels_json -> 'offset') = 'number'
            THEN (labels_json ->> 'offset')::BIGINT
        ELSE NULL
    END AS kafka_offset,
    unit,
    labels_json
FROM system_metrics;
```

Tại sao viết vậy: SQL view này biến `labels_json` thành cột typed và có default rõ ràng. Từ đây trở đi, dashboard chỉ đọc `metric_scope`, `metric_status`, `topic_name`, `failure_class`, `kafka_partition`, `kafka_offset`. Quy tắc parse sống ở **một chỗ**.

Guard chặn bug nằm ở ba điểm:

- `COALESCE(labels_json ->> 'scope', 'event')` chặn metric cũ hoặc metric append-only không có `scope`.
- `CASE WHEN metric_name IN ('feature_errors', 'write_failures') THEN 'error'` chặn dashboard hiểu nhầm metric lỗi là `ok` chỉ vì thiếu `labels_json.status`.
- `jsonb_typeof(...) = 'number'` đứng trước cast `::INTEGER` và `::BIGINT`, chặn panel nổ do có run cũ ghi label dạng string.

View này không đứng một mình. Dashboard summary chạy trên các lớp tiếp theo:

```sql
CREATE OR REPLACE VIEW vw_dashboard_run_total_metrics AS
SELECT DISTINCT ON (run_id, service_name, metric_name)
    ts,
    run_id,
    service_name,
    metric_name,
    metric_value,
    unit
FROM vw_dashboard_metric_events
WHERE metric_scope = 'run_total'
ORDER BY run_id, service_name, metric_name, ts DESC;
```

```sql
CREATE OR REPLACE VIEW vw_dashboard_run_summary AS
WITH run_ids AS (
    SELECT run_id FROM track_metadata
    UNION
    SELECT run_id FROM audio_features
    UNION
    SELECT run_id FROM system_metrics
),
run_totals AS (
    SELECT
        run_id,
        MAX(CASE WHEN service_name = 'ingestion' AND metric_name = 'tracks_total' THEN metric_value END)
            AS tracks_total,
        MAX(CASE WHEN service_name = 'processing' AND metric_name = 'silent_ratio' THEN metric_value END)
            AS reported_silent_ratio
    FROM vw_dashboard_run_total_metrics
    GROUP BY run_id
),
feature_summary AS (
    SELECT
        run_id,
        COUNT(*) AS segments_persisted,
        AVG(CASE WHEN silent_flag THEN 1.0 ELSE 0.0 END) AS observed_silent_ratio
    FROM audio_features
    GROUP BY run_id
)
SELECT
    run_ids.run_id,
    COALESCE(run_totals.tracks_total, 0.0) AS tracks_total,
    COALESCE(feature_summary.segments_persisted, 0) AS segments_persisted,
    COALESCE(run_totals.reported_silent_ratio, feature_summary.observed_silent_ratio, 0.0)
        AS silent_ratio
FROM run_ids
LEFT JOIN run_totals
    ON run_totals.run_id = run_ids.run_id
LEFT JOIN feature_summary
    ON feature_summary.run_id = run_ids.run_id;
```

Đến đây panel query trở nên mỏng và có thể đọc được. Ví dụ panel `Processing Latency Over Time` trong `infra/grafana/dashboards/system_health.json` không còn phải parse JSONB thủ công:

```json
{
  "rawSql": "SELECT\n  $__timeGroupAlias(ts, $__interval),\n  run_id AS metric,\n  ROUND(AVG(metric_value)::numeric, 3) AS value\nFROM vw_dashboard_metric_events\nWHERE $__timeFilter(ts)\n  AND service_name = 'processing'\n  AND metric_name = 'processing_ms'\nGROUP BY 1, 2\nORDER BY 1, 2;"
}
```

Lệnh verify:

```powershell
docker compose exec -T timescaledb psql -U audio_analytics -d audio_analytics -c "SELECT metric_name, metric_scope, metric_status, topic_name, kafka_partition, kafka_offset FROM vw_dashboard_metric_events ORDER BY ts DESC LIMIT 10;"
```

```powershell
docker compose exec -T timescaledb psql -U audio_analytics -d audio_analytics -c "SELECT run_id, tracks_total, segments_persisted, silent_ratio FROM vw_dashboard_run_summary ORDER BY run_id;"
```

### Bước 5.2. Mở `infra/grafana/provisioning/datasources/timescaledb.yaml`, `infra/grafana/provisioning/dashboards/dashboards.yaml`, rồi chốt mount trong `docker-compose.yml`

`provisioning` (Grafana tự nạp datasource/dashboard từ file khi container khởi động) phải là đường chuẩn. Nếu datasource và dashboard chỉ tồn tại sau vài cú click tay trong UI, bạn không có reproducibility: không diff được, không code-review được, không tái tạo được trên máy khác hay trong demo ngày mai.

Datasource phải được khóa bằng YAML:

```yaml
apiVersion: 1

datasources:
  - name: TimescaleDB
    uid: timescaledb
    type: postgres
    access: proxy
    url: timescaledb:5432
    database: audio_analytics
    user: audio_analytics
    secureJsonData:
      password: audio_analytics
    jsonData:
      sslmode: disable
      postgresVersion: 1600
      timescaledb: true
      maxOpenConns: 10
      maxIdleConns: 5
      connMaxLifetime: 14400
    isDefault: true
    editable: false
```

Dashboard provider cũng phải là file:

```yaml
apiVersion: 1

providers:
  - name: event-driven-audio-analytics
    orgId: 1
    folder: ""
    type: file
    disableDeletion: true
    updateIntervalSeconds: 10
    allowUiUpdates: false
    options:
      path: /var/lib/grafana/dashboards
```

Và `docker-compose.yml` phải mount đúng hai cây này:

```yaml
grafana:
  image: grafana/grafana:11.1.4
  ports:
    - "${GRAFANA_PORT:-3000}:3000"
  environment:
    GF_SECURITY_ADMIN_USER: "${GRAFANA_ADMIN_USER:-admin}"
    GF_SECURITY_ADMIN_PASSWORD: "${GRAFANA_ADMIN_PASSWORD:-admin}"
    GF_AUTH_ANONYMOUS_ENABLED: "true"
    GF_AUTH_ANONYMOUS_ORG_ROLE: "Viewer"
  volumes:
    - ./infra/grafana/provisioning:/etc/grafana/provisioning:ro,Z
    - ./infra/grafana/dashboards:/var/lib/grafana/dashboards:ro,Z
```

Tại sao viết vậy: YAML mới là source of truth của observability surface. UI chỉ là renderer. `uid: timescaledb` khóa datasource identity để dashboard JSON refer tới đúng nguồn dữ liệu. `allowUiUpdates: false` và `editable: false` khóa click-ops khỏi đường canonical.

Guard chặn bug:

- `uid: timescaledb` giữ cho dashboard JSON không bị gãy datasource reference sau khi import ở môi trường mới.
- `disableDeletion: true` chặn Grafana tự xóa dashboard file-provisioned khi folder scan thay đổi tạm thời.
- `allowUiUpdates: false` chặn dashboard bị “sửa nóng” trong UI rồi mất khỏi git diff.

Panel query thật trong `audio_quality.json` đọc luôn từ view summary, không dựa vào transform tay:

```json
{
  "rawSql": "SELECT\n  run_id AS metric,\n  ROUND((silent_ratio * 100.0)::numeric, 2) AS value\nFROM vw_dashboard_run_summary\nORDER BY last_seen_at DESC NULLS LAST, run_id DESC\nLIMIT 20;"
}
```

Lệnh verify:

```powershell
curl http://localhost:3000/api/health
```

```powershell
curl http://localhost:3000/api/dashboards/uid/audio-quality
```

```powershell
curl http://localhost:3000/api/dashboards/uid/system-health
```

### Bước 5.3. Mở `src/event_driven_audio_analytics/smoke/prepare_dashboard_demo_inputs.py`: khóa cứng deterministic demo inputs trước khi chạy dashboard

`deterministic input` (đầu vào được khóa cứng để mỗi lần chạy sinh cùng byte pattern, cùng metadata, cùng kỳ vọng) là xương sống của demo. Nếu bạn ném bừa audio vào pipeline, panel có lúc có `silent_ratio`, có lúc không; validation-failure có lúc hiện, có lúc biến mất. Demo như vậy không chứng minh gì ngoài may rủi.

Ba kịch bản phải được encode thành code, không encode bằng lời:

```python
HIGH_ENERGY_TRACK = DemoTrack(
    track_id=910001,
    artist_id=9101,
    genre="Synthetic-High-Energy",
    duration_s=6.0,
    description="Continuous high-energy tone for the baseline run.",
)
SILENT_ORIENTED_TRACK = DemoTrack(
    track_id=910002,
    artist_id=9102,
    genre="Synthetic-Silent-Oriented",
    duration_s=6.0,
    description="First segment silent, later segments energetic, so processing emits a non-zero silent_ratio.",
)
VALIDATION_FAILURE_TRACK = DemoTrack(
    track_id=910003,
    artist_id=9103,
    genre="Synthetic-Validation-Failure",
    duration_s=3.0,
    description="Fully silent track that fails ingestion validation and drives the error-rate panel.",
)
```

Waveform cũng phải khóa cứng:

```python
def _high_energy_waveform() -> list[int]:
    return _tone_samples(duration_s=HIGH_ENERGY_TRACK.duration_s, amplitude=0.55, frequency_hz=440.0)

def _silent_oriented_waveform() -> list[int]:
    return _silence_samples(duration_s=3.0) + _tone_samples(duration_s=3.0, amplitude=0.35, frequency_hz=660.0)

def _validation_failure_waveform() -> list[int]:
    return _silence_samples(duration_s=VALIDATION_FAILURE_TRACK.duration_s)
```

Toán học cho số sample vẫn phải khớp vào code:

```text
N = round(duration_s * 32000)
```

và dòng code thực thi là:

```python
sample_count = int(round(duration_s * sample_rate_hz))
```

Với track silent-oriented, nửa đầu phải là 3 giây im lặng thật, không phải “gần im lặng”:

```text
N_silent = round(3.0 * 32000) = 96000
```

và block code là:

```python
return _silence_samples(duration_s=3.0) + _tone_samples(duration_s=3.0, amplitude=0.35, frequency_hz=660.0)
```

Metadata CSV cũng phải dựng đúng header sandwich 3 dòng để ingestion đi cùng path với FMA-small:

```python
with csv_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle)
    writer.writerow(["", "artist", "set", "track", "track"])
    writer.writerow(["", "id", "subset", "genre_top", "duration"])
    writer.writerow(["track_id", "", "", "", ""])
    for track in tracks:
        writer.writerow(
            [
                track.track_id,
                track.artist_id,
                "small",
                track.genre,
                f"{track.duration_s:.2f}",
            ]
        )
```

Tại sao phải cứng hóa đúng 3 kịch bản này:

- `week7-high-energy` chứng minh pipeline có data tốt, RMS cao, `silent_ratio = 0`.
- `week7-silent-oriented` chứng minh có segment im lặng thật trong processing path, nên `silent_ratio` khác 0 nhưng validation vẫn pass.
- `week7-validation-failure` chứng minh dashboard nhìn thấy lỗi ingestion thật, không phải lỗi downstream giả lập.

Guard chặn bug:

- `_canonical_track_path(...)` ép mọi file vào layout `fma_small/000/000001.mp3`-style để metadata path và audio path khớp nhau.
- `_clamp_pcm_sample(...)` chặn sample amplitude vượt miền `[-1.0, 1.0]`, không làm wave invalid.
- CSV writer luôn ghi `subset=small`, chặn demo input tự phá semantics đã khóa từ ingestion.

Lệnh verify:

```powershell
docker compose run --rm --no-deps --entrypoint python ingestion -m event_driven_audio_analytics.smoke.prepare_dashboard_demo_inputs --output-root /app/artifacts/demo_inputs/dashboard-demo
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_prepare_dashboard_demo_inputs.py -q
```

---

**Phase 6 — Validation Ladder, Replay Smoke và Evidence**

### Bước 6.1. Mở `scripts/smoke/check-tree.ps1`, `scripts/smoke/check-pytest.sh`, `scripts/smoke/check-processing-writer-flow.sh`: đi từ rẻ đến đắt

`validation ladder` (thang xác minh; đi từ bước rẻ nhất, ít phụ thuộc nhất, lên bước đắt hơn, gần runtime thật hơn) phải được encode thành script độc lập. Nếu nhảy thẳng vào broker-backed smoke, bạn đốt thời gian container startup chỉ để phát hiện thiếu một file hoặc một import.

Bậc 1 là `check-tree`: chỉ xác nhận cây repo có đủ xương:

```powershell
$requiredPaths = @(
    "README.md",
    "docker-compose.yml",
    "pyproject.toml",
    "infra/kafka/create-topics.sh",
    "infra/kafka/create-topics.ps1",
    "infra/sql/002_core_tables.sql",
    "scripts/smoke/check-writer-flow.ps1",
    "scripts/smoke/check-processing-writer-flow.sh",
    "scripts/smoke/check-processing-writer-flow.ps1",
    "run-demo.ps1",
    "src/event_driven_audio_analytics/ingestion/app.py",
    "src/event_driven_audio_analytics/processing/app.py",
    "src/event_driven_audio_analytics/writer/app.py",
    "src/event_driven_audio_analytics/smoke/verify_writer_flow.py"
)
```

Bậc 2 là `check-pytest`: đóng toàn bộ verify unit/integration vào image `pytest`:

```sh
#!/usr/bin/env sh
set -eu

echo "Building pytest image..."
docker compose build pytest

if [ "$#" -gt 0 ]; then
  echo "Running pytest with explicit arguments..."
  docker compose run --rm pytest "$@"
else
  echo "Running full pytest suite..."
  docker compose run --rm pytest
fi
```

Bậc 3 mới là smoke có broker/DB/service sống thật:

```sh
echo "Starting Kafka and TimescaleDB for processing->writer smoke..."
docker compose up --build -d kafka timescaledb

echo "Bootstrapping Kafka topics..."
sh ./infra/kafka/create-topics.sh

echo "Starting processing and writer services in Compose..."
docker compose up -d --no-deps processing writer

echo "Running ingestion one-shot to feed Kafka..."
docker compose run --rm --no-deps ingestion

echo "Verifying current-run TimescaleDB outputs..."
docker compose run --rm --no-deps -e RUN_ID="$effective_run_id" --entrypoint python pytest \
  -m event_driven_audio_analytics.smoke.verify_writer_flow
```

Thứ tự này phải giữ nguyên:

```text
cost(check-tree) << cost(check-pytest) << cost(broker-backed smoke)
```

Tại sao viết vậy: bậc rẻ chặn bug cấu trúc, bậc giữa chặn bug logic/module, bậc đắt mới kiểm tra ordering, broker, checkpoint, restart, dashboard. Nếu đảo thứ tự, bạn sẽ “xác minh” bằng cách chờ container.

Guard chặn bug:

- `check-tree` fail-fast ngay khi thiếu file xương sống.
- `check-pytest` gom môi trường verify vào image cố định, tránh “máy tôi có package”.
- smoke script check service health, logs, topic existence, rồi mới kết luận pass.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-tree.ps1
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_prepare_dashboard_demo_inputs.py -q
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_restart_replay_smoke_verify.py -q
```

### Bước 6.2. Mở `scripts/smoke/check-restart-replay-flow.sh` và `src/event_driven_audio_analytics/smoke/verify_restart_replay_flow.py`: đạo diễn restart/replay bằng snapshot

Script shell phải làm đúng bốn việc: tạo baseline, chụp snapshot trước replay, restart service, rerun cùng `RUN_ID`, rồi verify snapshot sau replay.

Block điều phối cốt lõi là:

```sh
echo "Running first bounded ingestion pass for run_id=$effective_run_id..."
docker compose run --rm --no-deps \
  -e RUN_ID="$effective_run_id" \
  ingestion

echo "Writing restart/replay baseline snapshot..."
docker compose run --rm --no-deps \
  -e RUN_ID="$effective_run_id" \
  --entrypoint python \
  pytest \
  -m event_driven_audio_analytics.smoke.verify_restart_replay_flow \
  capture \
  --output "$baseline_path_container" >/dev/null

echo "Restarting processing and writer before replay..."
docker compose restart processing writer

echo "Re-running ingestion with the same run_id=$effective_run_id..."
docker compose run --rm --no-deps \
  -e RUN_ID="$effective_run_id" \
  ingestion

echo "Verifying replay-stable sink rows, metrics, checkpoints, and processing state..."
docker compose run --rm --no-deps \
  -e RUN_ID="$effective_run_id" \
  --entrypoint python \
  pytest \
  -m event_driven_audio_analytics.smoke.verify_restart_replay_flow \
  verify \
  --baseline "$baseline_path_container" \
  --output "$summary_path_container" >/dev/null
```

Python verify side định nghĩa snapshot bằng field thật, không phải một mẩu ghi chú ad-hoc:

```python
@dataclass(slots=True)
class RestartReplaySnapshot:
    run_id: str
    metadata_rows: tuple[MetadataRowSnapshot, ...]
    feature_rows: tuple[FeatureRowSnapshot, ...]
    ingestion_metric_counts: dict[str, int]
    processing_metric_counts: dict[str, int]
    writer_metric_counts: dict[str, int]
    checkpoint_offsets: dict[str, int]
    checkpoint_topics: tuple[str, ...]
    processing_state_segments: int
    processing_state_silent_segments: int
    processing_state_silent_ratio: float
    feature_silent_segments: int
    persisted_silent_ratio: float | None
```

Trọng số của replay path nằm ở công thức số record writer phải tiêu thụ mỗi bounded run:

```text
W = M + F + R + 2F
```

Trong đó:

- `M` là số metadata rows,
- `F` là số feature rows,
- `R = |EXPECTED_RUN_TOTAL_METRICS|`.

Repo current bounded smoke có:

```text
M = 2, F = 3, R = 4
```

nên:

```text
W = 2 + 3 + 4 + 2 * 3 = 15
```

và đó là lý do baseline unit snapshot chốt `writer.write_ms = 15` và `writer.rows_upserted = 15`.

Code verify tính đúng quan hệ tăng/giữ nguyên này:

```python
expected_processing_ms_count = (
    baseline.processing_metric_counts.get("processing_ms", 0) + expected_feature_count
)

expected_writer_metric_count = (
    baseline.writer_metric_counts.get("write_ms", 0) + expected_writer_record_count
)

expected_rows_upserted_count = (
    baseline.writer_metric_counts.get("rows_upserted", 0) + expected_writer_record_count
)
```

Guard chặn bug:

- `resolve_replay_run_id(...)` khóa `RUN_ID` không được trôi khỏi baseline.
- `validate_cleanup_run_id(...)` chặn path traversal khi cleanup `artifacts/runs/<run_id>`.
- verify layer so sánh `metadata_rows` và `feature_rows` theo snapshot tuple, không chỉ so count.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_restart_replay_smoke_verify.py -q
```

```powershell
docker compose run --rm --no-deps -e RUN_ID=week8-replay --entrypoint python pytest -m event_driven_audio_analytics.smoke.verify_restart_replay_flow capture --output /app/artifacts/demo/week8/restart-replay-baseline.json
```

```powershell
docker compose run --rm --no-deps -e RUN_ID=week8-replay --entrypoint python pytest -m event_driven_audio_analytics.smoke.verify_restart_replay_flow verify --baseline /app/artifacts/demo/week8/restart-replay-baseline.json --output /app/artifacts/demo/week8/restart-replay-summary.json
```

### Node 1. Baseline

Mở `scripts/smoke/check-restart-replay-flow.sh` và gõ đúng nhịp: reset stack, build image, start `kafka` + `timescaledb`, cố ý chạy preflight thất bại trước topic bootstrap, tạo topic, chạy preflight thành công, bật `processing` + `writer`, rồi mới chạy ingestion một lần đầu:

```sh
docker compose down --remove-orphans
docker compose build ingestion processing writer pytest
docker compose up --build -d kafka timescaledb
assert_expected_preflight_failure "ingestion" "missing required ingestion topics"
sh ./infra/kafka/create-topics.sh
docker compose run --rm --no-deps ingestion preflight
docker compose run --rm --no-deps processing preflight
docker compose run --rm --no-deps writer preflight
docker compose up -d --no-deps processing writer
docker compose run --rm --no-deps -e RUN_ID="$effective_run_id" ingestion
```

Tại sao viết vậy: baseline không chỉ là “run lần đầu”. Nó còn chứng minh startup gating: service phải fail-fast khi topic chưa có, rồi chuyển sang healthy path khi topic đã bootstrap.

Guard chặn bug:

- `assert_expected_preflight_failure(...)` ghi `preflight-fail-fast.txt` để bằng chứng fail-fast không bị mất.
- `assert_running_services processing writer` chặn restart script chạy tiếp trên service đã chết.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-tree.ps1
```

### Node 2. Snapshot Before

Snapshot baseline không phải ghi chú tay; nó là JSON sinh ra bởi `RestartReplaySnapshot.to_json()` sau khi `capture` pass:

```json
{
  "run_id": "week8-replay",
  "ingestion_metric_counts": {
    "artifact_write_ms": 1,
    "segments_total": 1,
    "tracks_total": 1,
    "validation_failures": 1
  },
  "processing_metric_counts": {
    "processing_ms": 3,
    "silent_ratio": 1
  },
  "writer_metric_counts": {
    "rows_upserted": 15,
    "write_ms": 15
  },
  "checkpoint_offsets": {
    "audio.features": "O_1(features)",
    "audio.metadata": "O_1(metadata)",
    "system.metrics": "O_1(metrics)"
  }
}
```

Phần phải đọc kỹ nhất là “row logic”, không chỉ “row count”:

```text
count(audio_features where (run_id, track_id, segment_idx) = (week8-replay, 2, 0)) = 1
```

```text
count(audio_features where (run_id, track_id, segment_idx) = (week8-replay, 2, 1)) = 1
```

```text
count(audio_features where (run_id, track_id, segment_idx) = (week8-replay, 2, 2)) = 1
```

Nói gọn: mỗi logical segment có đúng một row, và tổng số logical feature rows ở baseline là 3. `tracks_total = 1` cũng là đúng nghĩa snapshot replay-safe: metric đó chỉ chiếm **một row logic** cho run hiện tại, không phải một row mỗi lần rerun.

Guard chặn bug:

- `_assert_baseline_snapshot(...)` bác bỏ ngay nếu `mel_bins != 128` hoặc `mel_frames != 300`.
- cùng hàm đó buộc `silent_ratio count = 1` và `write_failures = 0`.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_restart_replay_smoke_verify.py -q -k "assert_baseline_snapshot_accepts_happy_path or assert_baseline_snapshot_rejects_processing_state_drift"
```

### Node 3. Restart & Replay

Đến node này, script chỉ làm đúng hai transition: restart consumer services, rồi rerun ingestion với **cùng** `RUN_ID`:

```sh
docker compose restart processing writer
sleep 5
assert_running_services processing writer

docker compose run --rm --no-deps \
  -e RUN_ID="$effective_run_id" \
  ingestion
```

Tại sao phải restart đúng `processing` và `writer`: đây là nơi restart-stable state và checkpoint semantics bị ép lộ ra. Ingestion chỉ được rerun lại để đẩy lại cùng logical chain. Nếu đổi `RUN_ID`, bạn không còn test replay nữa; bạn chỉ tạo run mới.

Guard chặn bug:

- `resolve_replay_run_id(configured_run_id, baseline_run_id)` chặn baseline và runtime mismatch.
- `check-restart-replay-flow.sh` đọc log sau replay và fail ngay nếu có `Processing failed` hoặc `Writer failed`.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_restart_replay_smoke_verify.py -q -k "resolve_replay_run_id_accepts_matching_env_and_baseline or resolve_replay_run_id_rejects_baseline_run_id_mismatch"
```

### Node 4. Snapshot After

Snapshot sau replay phải chứng minh ba lớp hành vi khác nhau: cái gì giữ nguyên, cái gì tăng, và offset đi tới đâu.

Những thứ **giữ nguyên**:

- `track_metadata` rows giữ nguyên y hệt baseline.
- `audio_features` rows giữ nguyên y hệt baseline.
- `ingestion_metric_counts` giữ nguyên y hệt baseline vì toàn bộ `run_total` metrics là replay-safe snapshot.
- `silent_ratio` row count giữ nguyên `1`.
- `processing_state_segments`, `processing_state_silent_segments`, `processing_state_silent_ratio` giữ nguyên.

Những thứ **tăng**:

```text
processing_ms_after = processing_ms_before + F = 3 + 3 = 6
```

```text
write_ms_after = write_ms_before + W = 15 + 15 = 30
```

```text
rows_upserted_after = rows_upserted_before + W = 15 + 15 = 30
```

Những thứ **phải tiến về phía trước**:

```text
O_2(topic) > O_1(topic)
```

cho từng `topic in {audio.metadata, audio.features, system.metrics}`.

Đó chính là logic trong `_assert_replay_snapshot(...)`:

```python
if snapshot.metadata_rows != baseline.metadata_rows:
    raise RuntimeError("Replay rerun drifted track_metadata rows for the same run_id.")
if snapshot.feature_rows != baseline.feature_rows:
    raise RuntimeError("Replay rerun drifted audio_features rows for the same run_id.")
if snapshot.ingestion_metric_counts != baseline.ingestion_metric_counts:
    raise RuntimeError("Replay rerun inflated replay-safe ingestion run_total metrics.")

if (
    snapshot.processing_metric_counts.get("silent_ratio", 0)
    != baseline.processing_metric_counts.get("silent_ratio", 0)
):
    raise RuntimeError("Replay rerun inflated replay-safe silent_ratio rows.")

for topic_name, baseline_offset in baseline.checkpoint_offsets.items():
    current_offset = snapshot.checkpoint_offsets.get(topic_name)
    if current_offset <= baseline_offset:
        raise RuntimeError(
            "Replay rerun did not advance the writer checkpoint offset "
            f"topic={topic_name} baseline={baseline_offset} current={current_offset}."
        )
```

Evidence file phải được sinh thành pack, không phải nhìn log xong rồi quên:

```sh
echo "Running restart/replay evidence path..."
sh ./scripts/smoke/check-restart-replay-flow.sh

echo "Running dashboard evidence path..."
sh ./scripts/demo/generate-dashboard-evidence.sh

write_demo_evidence_index
```

và file output chuẩn là:

```text
artifacts/demo/week8/restart-replay-baseline.json
artifacts/demo/week8/restart-replay-summary.json
artifacts/demo/week8/preflight-fail-fast.txt
artifacts/demo/week8/evidence-index.md
artifacts/demo/week7/dashboard-demo-summary.json
artifacts/demo/week7/grafana-api.json
artifacts/demo/week7/audio_quality.png
artifacts/demo/week7/system_health.png
artifacts/demo/week7/demo-artifact-notes.md
```

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_restart_replay_smoke_verify.py -q -k "assert_replay_snapshot_accepts_one_rerun_same_run_id or assert_replay_snapshot_rejects_feature_row_inflation or assert_replay_snapshot_rejects_checkpoint_stall"
```

```powershell
docker compose exec -T writer python -m event_driven_audio_analytics.smoke.verify_dashboard_demo
```

---

**Phase 7 — Bounded Demo Path, Honest Scope và Handoff**

### Bước 7.1. Mở `docker-compose.yml`, `event-contracts.md`, `ARCHITECTURE_CONTRACTS.md`, `IMPLEMENTATION_STATUS.md`: khóa bốn nhóm ranh giới sự thật

`overclaim` (tuyên bố vượt quá bằng chứng repo-backed) phải bị chặn bằng proof matrix. Ở phase này, bạn không “kể câu chuyện đẹp”. Bạn chỉ phân loại cái repo **đã chạy**, cái repo **đang conflict**, cái repo **cố ý hoãn**, và cái repo **không làm**.

#### Nhóm 1. Fact (Chạy thật)

```yaml
services:
  kafka:
  timescaledb:
  grafana:
  ingestion:
  processing:
  writer:
```

```text
event-contracts.md
- Envelope v1 khóa: event_id, event_type, event_version, trace_id, run_id, produced_at, source_service, idempotency_key, payload
- Scope v1 chỉ cho 4 primary topics: audio.metadata, audio.segment.ready, audio.features, system.metrics

ARCHITECTURE_CONTRACTS.md
- Claim-check boundary là artifacts/; Kafka chỉ chở small events
- Grafana là file-provisioned, không coi click-ops là canonical path

IMPLEMENTATION_STATUS.md
- Repo là runnable PoC với Docker Compose, Kafka KRaft, claim-check storage, TimescaleDB, Grafana
- Bounded restart/replay evidence ở artifacts/demo/week8/
- Deterministic dashboard demo evidence ở artifacts/demo/week7/
```

Tại sao xếp vào `Fact`: vì các mảnh này có file runtime/config/evidence tương ứng. Không có câu nào ở đây cần đoán.

Guard chặn bug: mọi phát biểu “chạy thật” đều phải trỏ được tới ít nhất một trong các nhóm sau:

- file config runtime như `docker-compose.yml`,
- contract/doc khóa như `event-contracts.md`,
- verify/evidence script như `generate-demo-evidence.sh`,
- artifact output như `restart-replay-summary.json`.

Lệnh verify:

```powershell
docker compose config
```

```powershell
Get-Content -Encoding utf8 event-contracts.md | Select-Object -First 40
```

#### Nhóm 2. Conflict (Xung đột)

Conflict thứ nhất là logical key của `audio_features` khác physical PK của Timescale:

```sql
CREATE TABLE IF NOT EXISTS audio_features (
    ts TIMESTAMPTZ NOT NULL,
    run_id TEXT NOT NULL,
    track_id BIGINT NOT NULL,
    segment_idx INTEGER NOT NULL,
    ...
    PRIMARY KEY (ts, run_id, track_id, segment_idx)
);

CREATE INDEX IF NOT EXISTS idx_audio_features_lookup
ON audio_features (run_id, track_id, segment_idx);
```

```text
K_logical = (run_id, track_id, segment_idx)
!=
K_physical = (ts, run_id, track_id, segment_idx)
```

Conflict thứ hai là RMS thật của signal silent là `-inf`, nhưng event transport v1 phải gửi số hữu hạn:

```python
def summarize_rms(waveform: np.ndarray) -> RmsSummary:
    mono_waveform = waveform.astype(np.float32, copy=False)
    if mono_waveform.size == 0:
        return RmsSummary(rms_linear=0.0, rms_dbfs=-math.inf)

def encode_rms_db_for_event(rms_dbfs: float, *, floor_db: float) -> float:
    if math.isfinite(rms_dbfs):
        return rms_dbfs
    return floor_db
```

```python
silence_threshold_db=float(os.getenv("SILENCE_THRESHOLD_DB", "-60.0"))
```

Tại sao xếp vào `Conflict`: cả hai vế đều “đúng” trong ranh giới riêng của nó, nhưng không đồng nhất với nhau. Vì vậy tài liệu phải giữ cả hai mặt, không được lén che một phía đi.

Guard chặn bug:

- với features, writer không được phép “đơn giản hóa” thành `ON CONFLICT` theo physical PK.
- với RMS, dashboard và writer phải đọc `silent_flag` cùng `rms`, không được diễn giải `-60.0` như một loudness vật lý thật.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/integration/test_writer_schema_contract.py -q -k "audio_features_mentions_logical_key_columns"
```

```powershell
Get-Content -Encoding utf8 src/event_driven_audio_analytics/processing/modules/rms.py | Select-Object -First 80
```

#### Nhóm 3. Deferred (Tạm hoãn)

`audio.dlq` là reserved, không phải active contract:

```sh
create_topic "audio.metadata"
create_topic "audio.segment.ready"
create_topic "audio.features"
create_topic "system.metrics"
create_topic "audio.dlq"
```

```text
event-contracts.md
- V1 does not model audio.dlq beyond noting that the topic remains reserved and outside the core contract set.
```

```python
"Ingestion failed for selected track; audio.dlq is reserved and not published in Week 4."
```

`welford_snapshots` có bảng nhưng chưa có producer path:

```sql
CREATE TABLE IF NOT EXISTS welford_snapshots (
    run_id TEXT NOT NULL,
    service_name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    count BIGINT NOT NULL,
    mean DOUBLE PRECISION NOT NULL,
    m2 DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, service_name, metric_name)
);
```

```text
IMPLEMENTATION_STATUS.md
- Fact: welford_snapshots exists in SQL, but the current processing runtime does not persist that state.
```

Tại sao xếp vào `Deferred`: repo thừa nhận chỗ để dành sẵn, nhưng chưa claim runtime path hoàn chỉnh, chưa có end-to-end evidence, chưa có contract/test đầy đủ cho nó.

Guard chặn bug:

- không được trình bày `audio.dlq` như “đã có DLQ”.
- không được trình bày `welford_snapshots` như “đã persisted Welford state”.

Lệnh verify:

```powershell
Get-Content -Encoding utf8 infra/kafka/create-topics.sh | Select-Object -First 40
```

```powershell
Get-Content -Encoding utf8 infra/sql/002_core_tables.sql | Select-Object -Last 20
```

#### Nhóm 4. Out-of-scope (Ngoài phạm vi)

```text
AGENTS.md
- Out of scope: Kubernetes, service mesh, HA/DR, multi-node Kafka, autoscaling, exactly-once end-to-end to an external DB, full schema-governance stack, production object storage/IAM, model serving, training pipelines, and full observability backends.

IMPLEMENTATION_STATUS.md
- Exactly-once end to end is out of scope
- Kubernetes, HA/DR, multi-node Kafka are deferred / outside the bounded demo path
- The default demo path is bounded, not benchmark-scale
```

Tại sao xếp vào `Out-of-scope`: đây không phải feature “chưa kịp làm”. Đây là biên được khóa ngay từ đầu để PoC không tự giả làm production platform.

Guard chặn bug: mọi slide/demo/runbook về sau nếu nhắc các mục này phải gắn nhãn out-of-scope ngay tại chỗ, không để người đọc tưởng repo đã có benchmark, exactly-once, hay HA.

Lệnh verify:

```powershell
Get-Content -Encoding utf8 AGENTS.md | Select-String -Pattern "Out of scope|Exactly-once|HA/DR|Kubernetes"
```

```powershell
Get-Content -Encoding utf8 IMPLEMENTATION_STATUS.md | Select-String -Pattern "Exactly-once|Kubernetes|HA/DR|bounded"
```

### Bước 7.2. Handoff: 5 quy tắc “đừng phá vỡ” cho người kế nhiệm

1. Đừng phá claim-check boundary. `event-contracts.md` và `ARCHITECTURE_CONTRACTS.md` đã khóa nguyên tắc Kafka chỉ chở event nhỏ; raw PCM, waveform blob, tensor lớn không được quay lại broker.
2. Đừng commit offset trước khi payload và checkpoint đã bền. `writer/pipeline.py` cộng với `writer/modules/offset_manager.py` đã khóa điều kiện `rows_written > 0` và `checkpoint_rows > 0` trước `consumer.commit()`.
3. Đừng đổi `upsert_features.py` thành `ON CONFLICT` ngây thơ theo physical PK. `infra/sql/002_core_tables.sql` và `writer/modules/upsert_features.py` đang giải đúng conflict `logical key` vs `Timescale hypertable PK`.
4. Đừng để Grafana query raw JSONB trực tiếp. `infra/sql/003_operational_views.sql` là contract normalization layer; dashboard JSON chỉ nên query qua `vw_dashboard_metric_events`, `vw_dashboard_run_validation`, `vw_dashboard_run_summary`.
5. Đừng overclaim `audio.dlq` hay `welford_snapshots`. `infra/kafka/create-topics.sh`, `infra/sql/002_core_tables.sql`, `IMPLEMENTATION_STATUS.md`, và log message trong `ingestion/pipeline.py` đều nói rõ: một cái mới reserved, một cái mới có bảng.

Lệnh verify:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-tree.ps1
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_prepare_dashboard_demo_inputs.py -q
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke\check-pytest.ps1 tests/unit/test_restart_replay_smoke_verify.py -q
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\generate-demo-evidence.ps1
```

Dừng ở đây. CHUNK 5 hoàn tất toàn bộ tài liệu.
