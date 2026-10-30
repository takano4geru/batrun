# 福岡都市高速 環状線ドライブ（Flutter モック）

`../course-data/` の実データ（環状線内回り 34.68km、10m 区間のカーブ・標高・トンネル、沿線建物）を使って、
OutRun 風の擬似3Dで都市高速を周回できるモックです。Flutter 3.47.7 / Dart 3.13 で作成し、Web で動作確認しています。

![走行中](screenshots/01_start_elevated.png)

## 動かし方

```
flutter pub get
flutter run -d chrome          # 開発
flutter build web --release    # 公開用 (build/web)
```

ビルド済みの Web 版は `web_build/` にあります。`cd web_build && python3 -m http.server` で開けます（file:// 直開きは不可）。

## 操作

| キー | 動作 |
|---|---|
| ↑ / W | アクセル |
| ↓ / S / Space | ブレーキ |
| ← → / A D | ハンドル |
| T | 時間帯 (昼 → 夕方 → 夜) |
| P | ドット表示 (480×270 低解像度描画) の切替 |
| C | カーブ強調 (2.5倍 → 5倍 → 実寸) |
| Esc | ポーズ |

画面上のボタンでタッチ操作もできます。

動作確認用に URL パラメータで開始状態を指定できます: `?s=29000&speed=80&tod=night&auto=1`
（s: 開始位置[m], speed: km/h, tod: day/evening/night, auto=1: すぐ走り出す）。

## 中身

| ファイル | 内容 |
|---|---|
| `lib/course.dart` | コースデータの読み込みと補間 (標高・方位・次のランプ・近くの名所) |
| `lib/game.dart` | 自車の物理 (加減速・遠心力・壁・一般車との接触)、一般車、ラップ計測 |
| `lib/renderer.dart` | 擬似3D描画。セグメントを奥から手前へ描く。高架の地面・橋脚、建物の箱、トンネルと坑口、背景の山並みと実際の方角に見える福岡タワー |
| `lib/hud.dart` | 速度・ラップ・次のランプ・名所・ミニマップ・出典表示、タッチボタン |
| `tool/build_assets.py` | `course-data/` から `assets/course_data.json` (約560KB) を生成 |

アセットの再生成: `python3 tool/build_assets.py ../course-data assets/course_data.json`
（道路から 170m 以内の建物と 30m 以上の高い建物、計 16,074 棟を採用。建物は PLATEAU 由来）

## 割り切っている点

- カーブは実データのままだと緩く見えるため 2.5 倍に強調しています (C キーで変更可)。
- 建物は外形ではなく最小外接矩形の箱で描いています。
- 標高は推定値です (course-data/README.md 参照)。
- 一般車は車線変更しない一定速度の車です。

## 出典

地図データ © OpenStreetMap contributors (ODbL) / Overture Maps Foundation、地盤標高: 国土地理院 標高タイルを加工して作成。
建物: 出典：国土交通省 Project PLATEAU（福岡市 3D都市モデル）を加工して作成（建物名の一部は OSM 由来）。福岡タワーは PLATEAU に含まれないため OSM の位置で描画。
フォント: DotGothic16 (SIL Open Font License)。
