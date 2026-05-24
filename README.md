# Raspberry Pi 5 Person Flow Analytics

Ubuntu を入れた Raspberry Pi 5 上で、ATOMS3RM12 から取得したストリーミング画像に対して YOLO11 による人物検知を行い、人流データを収集・分析する Python プログラムです。

この README は、まず実装方針とセットアップ手順を固めるためのものです。後続で Python 実装を追加する前提で、必要な依存関係、設定、出力データ形式を定義しています。

## 目的

取得した映像から `person` のみを検知し、フレーム間で人物を追跡して以下の変数を記録します。

- `left_to_right`: 左から右へ通過した人数
- `right_to_left`: 右から左へ通過した人数
- `stopped`: 一定時間以上ほぼ同じ位置に立ち止まった人数またはイベント数
- `active_tracks`: 現在追跡中の人物数
- `timestamp`: 記録時刻
- `track_id`: 追跡対象ごとの ID
- `bbox`: 人物の検出矩形
- `center_x`, `center_y`: 人物矩形の中心座標
- `direction`: `left_to_right`, `right_to_left`, `stopped`, `unknown`
- `dwell_time_sec`: 立ち止まり、または滞留時間

## 想定構成

```text
ATOMS3RM12
  -> HTTP MJPEG / RTSP / snapshot endpoint
  -> Raspberry Pi 5 Ubuntu
  -> OpenCV frame capture
  -> Ultralytics YOLO11 person detection + tracking
  -> CSV / SQLite / JSONL output
  -> 集計・分析
```

ATOMS3RM12 側の配信方式は環境によって異なる可能性があるため、プログラムでは `STREAM_URL` を設定で差し替えられるようにします。

例:

```text
http://192.168.1.50:81/stream
rtsp://192.168.1.50:8554/stream
http://192.168.1.50/capture
```

## 必要環境

- Raspberry Pi 5
- Ubuntu 24.04 LTS などの 64-bit Ubuntu
- Python 3.10 以上
- uv
- ATOMS3RM12 が同一ネットワーク上で画像を配信できること
- カメラの設置位置が固定されていること

## セットアップ

### 1. uv プロジェクトを作成

まだ `pyproject.toml` がない場合:

```bash
uv init
```

### 2. 依存関係を追加

Raspberry Pi 5 では CPU 実行を基本にします。まずは以下を入れます。

```bash
uv add ultralytics lap opencv-python numpy pandas pydantic pydantic-settings rich
```

SQLite 出力だけなら標準ライブラリで足ります。グラフ化や後処理も行う場合は追加します。

```bash
uv add matplotlib seaborn
```

ヘッドレス運用で GUI 表示が不要な場合、`opencv-python` の代わりに以下を使う構成も検討できます。

```bash
uv remove opencv-python
uv add opencv-python-headless
```

Raspberry Pi 上で `ultralytics` の依存として PyTorch がうまく入らない場合は、環境に合う PyTorch を先に入れてから `ultralytics` を追加します。失敗したコマンドとエラーに合わせて調整してください。

## 現場での起動

現場担当者が使う場合は、長いコマンドではなく以下だけを実行します。

```bash
./scripts/start_preview.sh
```

起動すると、スマホやPCで開くURLが表示されます。固定URLを設定済みの場合は `.local` のURLも表示されます。

```text
http://takota.local:8080
http://192.168.xx.xx:8080
```

同じテザリングまたはWi-Fiに接続したスマホ/PCのブラウザで、そのURLを開きます。停止する場合は、起動したターミナルで `Ctrl+C` を押します。
iPhoneテザリングの場合、ラズパイ側のIPは `172.20.10.x` になることがあります。`172.20.10.1` は通常iPhone側のアドレスなので、ブラウザで開くのは `./scripts/show_preview_url.sh` に表示されるラズパイ側のIPです。

### 固定URLにする場合

モニターなしで運用する場合は、IPではなく固定ホスト名のURLを使います。初回だけSSHなどでラズパイに入り、以下を実行します。

```bash
./scripts/setup_fixed_preview_url.sh
```

これでブラウザから以下のURLで開けるようになります。

```text
http://takota.local:8080
```

別の名前にしたい場合は、名前を指定します。

```bash
./scripts/setup_fixed_preview_url.sh takota-01
```

この場合のURLは `http://takota-01.local:8080` です。iPhoneテザリングでも、ラズパイと開く端末が同じテザリングに接続されていればこのURLを使います。反映されない場合は `sudo reboot` でラズパイを再起動してください。

カメラだけ確認する場合:

```bash
./scripts/check_camera.sh
```

プレビューURLだけ確認する場合:

```bash
./scripts/show_preview_url.sh
```

プレビューサーバーに接続できない場合は、SSHで以下を実行して状態を確認します。

```bash
./scripts/check_preview_server.sh
```

`active` かつ `8080` 番で待ち受けていれば、ラズパイ側のサーバーは起動しています。ブラウザ側で接続できない場合は、同じテザリング/Wi-Fiに接続しているか、Wi-Fiルーターのゲストネットワークやプライバシーセパレーターで端末同士の通信がブロックされていないかを確認してください。

初回起動時に `.env` がなければ、`.env.example` から自動作成します。設定を変える場合は `.env` を編集します。

### 電源投入時に自動起動する場合

モニターがない現場では、この設定を推奨します。ラズパイに電源を入れるだけでプレビューと計測が起動します。

初回だけ、SSHなどでラズパイに入り、以下を実行します。

```bash
./scripts/install_autostart_service.sh
```

設定後、ラズパイを再起動します。

```bash
sudo reboot
```

再起動後、同じテザリングまたはWi-Fiに接続したスマホ/PCで以下を開きます。

```text
http://<RASPI_IP>:8080
```

`install_autostart_service.sh` は `systemctl --user enable` と `loginctl enable-linger` を設定します。これにより、ユーザーがログインしていない状態でも systemd user service が起動できます。
自動起動時は、iPhoneテザリングのIP取得が遅れる場合に備えて最大120秒待ってからURL候補を表示します。プレビューサーバー自体は `0.0.0.0` で待ち受けるため、起動後にテザリングへ接続された場合も同じポートでアクセスできます。

### プレビュー画面から電源を切る場合

プレビュー画面の電源終了ボタンはデフォルトでは無効です。使う場合は、ラズパイ上で初回だけ以下を実行します。

```bash
./scripts/install_preview_shutdown.sh
```

このスクリプトは、現在のユーザーが `poweroff` だけをパスワードなしで実行できる sudoers 設定を `/etc/sudoers.d/` に追加し、`.env` に以下を設定します。

```env
PREVIEW_SHUTDOWN_ENABLED=true
PREVIEW_SHUTDOWN_COMMAND="sudo -n /usr/sbin/poweroff"
```

`poweroff` のパスは環境に合わせて自動検出されます。反映するにはプレビューまたは自動起動サービスを再起動します。

```bash
systemctl --user restart takota-people-flow.service
```

安全対策として、サーバー側では localhost / LAN / テザリングなどのプライベートアドレスからの操作だけを受け付け、画面側とAPI側の両方で確認語句 `電源を切る` を要求します。無効化する場合は `.env` の `PREVIEW_SHUTDOWN_ENABLED=false` に戻し、必要に応じて `/etc/sudoers.d/takota-preview-shutdown-<ユーザー名>` を削除してください。

今すぐ手動で開始する場合:

```bash
systemctl --user start takota-people-flow.service
```

状態確認:

```bash
systemctl --user status takota-people-flow.service
```

ログ確認:

```bash
journalctl --user -u takota-people-flow.service -f
```

停止:

```bash
systemctl --user stop takota-people-flow.service
```

自動起動を使う場合は、現場投入前に一度 `./scripts/start_preview.sh` で手動起動できることを確認してください。

### iPhoneテザリングが切れた場合に自動復旧する

iPhoneに電話が入るなどしてテザリングが一度切れる場合は、ラズパイ側で NetworkManager の再接続を監視できます。初回だけ以下を実行します。

```bash
./scripts/install_tethering_recovery_service.sh
systemctl --user start takota-tethering-recovery.service
```

復旧監視は、ラズパイのIPv4アドレスが一定時間消えたら段階的に復旧を試します。まず保存済みの自動接続プロファイルへ再接続し、失敗が続く場合は Wi-Fi の off/on、さらに失敗する場合は NetworkManager の再起動へ進みます。iPhone側の「インターネット共有」が再び利用可能になっている必要があります。

接続プロファイル名を固定したい場合は `.env` に以下を追加します。名前は `nmcli connection show` で確認できます。

```env
TETHER_CONNECTION_NAME="iPhone"
TETHER_RECOVERY_REQUIRE_CONNECTION_NAME=true
```

現場で別Wi-Fiに接続されてしまう場合は、iPhoneテザリング以外のWi-Fi自動接続を無効化します。

```bash
nmcli connection show
./scripts/lock_tether_connection.sh "iPhone"
systemctl --user restart takota-tethering-recovery.service
```

この設定後は、`TETHER_CONNECTION_NAME` の接続が有効でない限り「復旧済み」と判定しません。別Wi-Fiへ接続されても復旧監視が続き、対象外Wi-Fiは切断します。

確認間隔を変える場合:

```env
TETHER_RECOVERY_CHECK_INTERVAL_SEC=10
TETHER_RECOVERY_MISSING_CONFIRM_SEC=20
TETHER_RECOVERY_WAIT_SEC=60
TETHER_RECOVERY_STAGE_WAIT_SEC=30
```

NetworkManager の再起動には sudo が必要です。パスワード入力なしで実行できない場合は、その段階だけ失敗としてログに残り、監視は継続します。

通常、プレビューサーバーは `0.0.0.0` で待ち受け続けるため、テザリング復旧後にアプリを再起動する必要はありません。IP変更後にアプリも再起動したい場合だけ、以下を `.env` に追加します。

```env
TETHER_RECOVERY_RESTART_PREVIEW_SERVICE=true
```

最後の手段としてラズパイを自動再起動したい場合だけ、以下を `.env` に追加します。

```env
TETHER_RECOVERY_REBOOT_ENABLED=true
```

この場合も `sudo -n reboot` がパスワードなしで実行できる必要があります。現場投入前に sudoers を設定し、短時間だけテザリングを切ってログを確認してください。

sudoers 設定と `.env` 更新をまとめて行う場合:

```bash
./scripts/install_tethering_recovery_sudoers.sh
systemctl --user restart takota-tethering-recovery.service
```

状態確認:

```bash
systemctl --user status takota-tethering-recovery.service
```

ログ確認:

```bash
journalctl --user -u takota-tethering-recovery.service -f
```

## 実行予定コマンド

実装後は以下のように起動できる形にします。

```bash
uv run python -m takota_people_flow \
  --stream-url "http://192.168.1.50:81/stream" \
  --model models/yolo11n.pt \
  --output data/people_flow.csv
```

低負荷で試す場合:

```bash
uv run python -m takota_people_flow \
  --stream-url "http://192.168.1.50:81/stream" \
  --model models/yolo11n.pt \
  --imgsz 416 \
  --frame-skip 2
```

YOLO を使う前に、ATOMS3RM12 の映像が OpenCV で読めるかだけ確認する場合:

```bash
uv run takota-people-flow \
  --stream-url 0 \
  --check-stream \
  --max-frames 30
```

YOLO11 の人物検知と tracking を接続して確認する場合:

```bash
uv run takota-people-flow \
  --stream-url 0 \
  --model models/yolo11n.pt \
  --device cpu \
  --track \
  --max-frames 10 \
  --frame-skip 2
```

左右通過と立ち止まりイベントを CSV に保存する場合:

```bash
uv run takota-people-flow \
  --stream-url 0 \
  --model models/yolo11n.pt \
  --device cpu \
  --track \
  --max-frames 300 \
  --frame-skip 2 \
  --line-x-ratio 0.5 \
  --stop-speed-px-per-sec 12 \
  --stop-duration-sec 3 \
  --output data/people_flow.csv
```

FPS と検知精度を調整する場合は、まず表を出さずに短時間の実測をします。

```bash
uv run takota-people-flow \
  --stream-url 0 \
  --model models/yolo11n.pt \
  --device cpu \
  --track \
  --no-table \
  --max-frames 30 \
  --camera-width 480 \
  --camera-height 320 \
  --camera-fps 30 \
  --camera-fourcc MJPG \
  --imgsz 416 \
  --conf 0.35 \
  --frame-skip 2 \
  --output data/people_flow.csv
```

モニターがない現場でスマホやPCのブラウザからライブプレビューを見る場合:

```bash
uv run takota-people-flow \
  --stream-url 0 \
  --model models/yolo11n.pt \
  --device cpu \
  --track \
  --preview-server \
  --preview-host 0.0.0.0 \
  --preview-port 8080 \
  --run-forever \
  --no-table \
  --camera-width 480 \
  --camera-height 320 \
  --camera-fps 30 \
  --camera-fourcc MJPG \
  --imgsz 320 \
  --conf 0.35 \
  --frame-skip 2 \
  --output data/people_flow.csv
```

ラズパイの IP アドレスを確認します。

```bash
hostname -I
```

スマホやPCから以下を開きます。`<RASPI_IP>` は `hostname -I` で出た IP に置き換えます。

```text
http://<RASPI_IP>:8080
```

プレビューには人物 bbox、`track_id`、判定ライン、処理 FPS、直近イベントが重ね描きされます。画面上部にはバッジ消化数の手動カウントも表示され、`1バッジ消化` ボタンを押すと `data/badge_counts.csv` に捌き切った時刻が記録されます。押し間違えた場合は `1つ戻す` で直前相当の1バッジ分を取り消せます。テザリング環境では `--camera-width 320 --camera-height 240 --imgsz 320 --frame-skip 3 --preview-jpeg-quality 60` にすると通信量とCPU負荷を下げられます。

さらに軽くする場合:

```bash
uv run takota-people-flow \
  --stream-url 0 \
  --model models/yolo11n.pt \
  --device cpu \
  --track \
  --no-table \
  --max-frames 30 \
  --camera-width 320 \
  --camera-height 240 \
  --camera-fps 30 \
  --camera-fourcc MJPG \
  --imgsz 320 \
  --conf 0.4 \
  --frame-skip 3 \
  --output data/people_flow.csv
```

## 推奨モデル

Raspberry Pi 5 では最初に `models/yolo11n.pt` を使います。

- `models/yolo11n.pt`: 最軽量。ラズパイでの初期検証向き
- `yolo11s.pt`: 精度を上げたい場合。ただし FPS は落ちる

人物検知のみを使うため、COCO クラスの `person` だけを対象にします。

## 人流判定の考え方

### 1. 人物検知

YOLO11 でフレームごとに人物矩形を取得します。

### 2. トラッキング

Ultralytics の tracking 機能、または ByteTrack を使って、同じ人物に `track_id` を付け続けます。

### 3. 通過方向

画面中央付近に仮想ラインを置き、人物中心点がラインをまたいだ方向で判定します。

- 中心点が左側から右側へ移動: `left_to_right`
- 中心点が右側から左側へ移動: `right_to_left`

設定例:

```text
line_x_ratio = 0.5
```

これは画面幅の 50% の位置に縦ラインを置くという意味です。

### 4. 立ち止まり判定

同じ `track_id` の中心点移動量が一定以下の状態が、指定秒数以上続いたら `stopped` とします。

設定例:

```text
stop_speed_px_per_sec = 12
stop_duration_sec = 3.0
```

## 設定項目

実装では CLI 引数または `.env` で以下を指定できるようにします。

| 項目 | 例 | 説明 |
| --- | --- | --- |
| `STREAM_URL` | `http://192.168.1.50:81/stream` | ATOMS3RM12 の映像 URL |
| `MODEL` | `models/yolo11n.pt` | YOLO11 モデル |
| `DEVICE` | `cpu` | 推論デバイス |
| `IMGSZ` | `416` | 推論画像サイズ |
| `CONF` | `0.35` | 検知信頼度しきい値 |
| `IOU` | `0.5` | NMS / tracking 用 IOU |
| `CAMERA_WIDTH` | `480` | UVC カメラに要求する入力幅 |
| `CAMERA_HEIGHT` | `320` | UVC カメラに要求する入力高さ |
| `CAMERA_FPS` | `15` | UVC カメラに要求する FPS |
| `CAMERA_FOURCC` | `MJPG` | UVC カメラに要求するピクセル形式 |
| `FRAME_SKIP` | `2` | 何フレームに 1 回推論するか |
| `MAX_FRAMES` | `30` | 接続確認時に読み取るフレーム数 |
| `LINE_X_RATIO` | `0.5` | 左右通過判定ライン |
| `STOP_SPEED_PX_PER_SEC` | `12` | 立ち止まり判定の速度しきい値 |
| `STOP_DURATION_SEC` | `3.0` | 立ち止まり判定の継続秒数 |
| `OUTPUT` | `data/people_flow.csv` | 出力先 |
| `BADGE_OUTPUT` | `data/badge_counts.csv` | 手動バッジ消化数の出力先 |
| `PREVIEW_HOST` | `0.0.0.0` | プレビューHTTPサーバの待受ホスト |
| `PREVIEW_PORT` | `8080` | プレビューHTTPサーバのポート |
| `PREVIEW_JPEG_QUALITY` | `80` | プレビューJPEG品質 |
| `PREVIEW_SHUTDOWN_ENABLED` | `false` | プレビュー画面からの電源終了を有効化する |
| `PREVIEW_SHUTDOWN_COMMAND` | 空 | 電源終了時に実行する固定コマンド |

## 出力 CSV 例

```csv
timestamp,track_id,event,direction,center_x,center_y,dwell_time_sec,bbox_x1,bbox_y1,bbox_x2,bbox_y2,confidence
2026-04-27T10:15:12.123+09:00,7,cross,left_to_right,402,233,1.42,360,120,444,346,0.82
2026-04-27T10:15:18.456+09:00,8,stopped,stopped,188,251,3.04,150,131,226,366,0.79
```

## バッジ消化数 CSV 例

プレビュー画面の `営業開始` ボタンを押すと営業開始時刻を記録し、`1バッジ消化` ボタンを押すたびにバッジを捌き切った時刻を `data/badge_counts.csv` へ追記します。バッジ途中で営業終了する場合は、`途中` に進捗を `0.0` から `0.99` で入力して `営業終了` を押します。たとえば半分程度まで進んでいれば `0.5` バッジとして、その日のバッジ数に小数で加算します。

```csv
timestamp,event,badges_delta,total_badges,partial_progress
2026-04-27T10:00:00+09:00,start,0,0,0.0
2026-04-27T13:30:00+09:00,consume,1,1,0.0
2026-04-27T17:00:00+09:00,end,0.5,1.5,0.5
2026-04-28T10:00:00+09:00,start,0,1.5,0.0
2026-04-28T11:30:00+09:00,consume,0.5,2.0,0.0
2026-04-28T11:31:00+09:00,undo,-0.5,1.5,0.0
```

日ごとのバッジ数と、週ごとの累計バッジ数・捌き切った時刻を確認する場合:

```bash
uv run takota-people-flow \
  --aggregate-badges \
  --badge-output data/badge_counts.csv
```

集計表の `partial` は営業終了時点でその日に小数加算した途中進捗です。翌日にそのバッジを捌き切った場合、`1バッジ消化` は残り分だけを加算します。たとえば前日に `0.5` を記録していれば、翌日の完了時は `0.5` バッジだけ加算します。ただし週を跨ぐ場合、途中進捗は廃棄して翌週へ持ち越しません。時間は翌日に持ち越しません。

## 集計例

保存済み CSV を30分ごとに集計し、表形式で確認できます。実行すると同じ内容が `data/people_flow_summary.csv` にも保存されます。

```bash
uv run takota-people-flow \
  --aggregate \
  --output data/people_flow.csv
```

保存先を変える場合:

```bash
uv run takota-people-flow \
  --aggregate \
  --output data/people_flow.csv \
  --aggregate-output data/people_flow_summary.csv
```

集計間隔を変える場合:

```bash
uv run takota-people-flow \
  --aggregate \
  --aggregate-interval-minutes 15 \
  --output data/people_flow.csv
```

バッジ消化数の集計は、日別が `data/badge_daily_summary.csv`、週別が `data/badge_weekly_summary.csv` に保存されます。保存先を変える場合:

```bash
uv run takota-people-flow \
  --aggregate-badges \
  --badge-output data/badge_counts.csv \
  --badge-daily-output data/badge_daily_summary.csv \
  --badge-weekly-output data/badge_weekly_summary.csv
```

出力例:

```text
People flow summary (30 min)
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━┓
┃ start                  ┃ end                    ┃ L->R ┃ R->L ┃ stopped ┃ events ┃ tracks ┃ peak ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━╇━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━┩
│ 2026-04-27 13:00       │ 2026-04-27 13:30       │   25 │   22 │       9 │     56 │     12 │    2 │
└────────────────────────┴────────────────────────┴──────┴──────┴─────────┴────────┴────────┴──────┘
```

## パフォーマンス調整

Raspberry Pi 5 で FPS が不足する場合は、以下の順に調整します。

1. `models/yolo11n.pt` を使う
2. `IMGSZ` を `416` または `320` に下げる
3. `FRAME_SKIP` を `2` 以上にする
4. 入力映像の解像度を下げる
5. GUI プレビューを無効化する
6. 必要なら Hailo / Coral などの外部アクセラレータを検討する

今回確認した ATOMS3RM12 の UVC フォーマットは `1920x1080`, `480x320`, `320x240` です。OpenCV で解像度指定を効かせる場合は `/dev/video0` ではなく `--stream-url 0` のようにカメラ番号で指定します。実測結果の `processing_fps` が低い場合は、まず `--imgsz 320`、`--frame-skip 3`、`--camera-width 320 --camera-height 240` を試します。検出漏れが多い場合は、`--conf 0.25` に下げるか、`--imgsz 416` に戻します。誤検出が多い場合は、`--conf 0.45` 以上に上げます。

## ディレクトリ構成予定

```text
.
├── README.md
├── pyproject.toml
├── .env.example
├── data/
│   └── .gitkeep
└── src/
    └── takota_people_flow/
        ├── __init__.py
        ├── __main__.py
        ├── config.py
        ├── capture.py
        ├── detector.py
        ├── tracker.py
        ├── events.py
        ├── preview.py
        ├── output.py
        └── analysis.py
```

## 実装予定モジュール

- `capture.py`: ATOMS3RM12 の stream URL からフレームを取得
- `detector.py`: YOLO11 で人物検知
- `tracker.py`: track_id と人物移動履歴を管理
- `events.py`: 左右通過、立ち止まり、滞留を判定
- `preview.py`: ブラウザ向け MJPEG ライブプレビュー
- `output.py`: CSV / JSONL / SQLite に保存
- `analysis.py`: 保存済みデータの集計
- `__main__.py`: CLI エントリポイント

## 注意点

- カメラが斜め向きの場合、単純な左右判定では実際の動線とずれることがあります。その場合は、判定ラインを任意の 2 点で定義する方式に変更します。
- 立ち止まり判定はピクセル移動量ベースのため、カメラから遠い人物ほど動きが小さく見えます。設置後にしきい値調整が必要です。
- 個人識別は行いません。保存するのは検出・追跡 ID と位置情報だけです。
- 長時間運用する場合は、CSV より SQLite または日付別 JSONL の方が扱いやすくなります。

## 次の作業

1. `pyproject.toml` とパッケージ構成を作成
2. `STREAM_URL` から OpenCV でフレーム取得
3. YOLO11 の人物検知と tracking を接続
4. 左右通過と立ち止まりイベントを CSV 出力
5. ラズパイ5上で FPS と検知精度を調整
