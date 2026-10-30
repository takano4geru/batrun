# 出典とデータのライセンス

このリポジトリのデータは、以下の公開データを加工して作成しています。

## OpenStreetMap / Overture Maps Foundation（コース線形・道路名・建物名の一部）

- 地図データ © OpenStreetMap contributors
- Overture Maps Foundation の transportation データ（OSM 由来）
- ライセンス: Open Database License (ODbL) 1.0 https://opendatacommons.org/licenses/odbl/1-0/
- 該当ファイル: `course-data/course_ring_inner.json`、`course-data/course_ring_inner_centerline.csv`、`course-data/scenery_ring_inner_osm.*`、`flutter-app/assets/course_data.json`（コース部分と `name_src: "OSM"` の建物名）
- これらの派生データベースは ODbL 1.0 のもとで提供します。

## 国土交通省 Project PLATEAU（建物の外形・高さ・用途）

- 出典：国土交通省 Project PLATEAU 福岡市 3D都市モデル（2024年度）を加工して作成
- データ入手先: https://www.geospatial.jp/ckan/dataset/plateau-40130-fukuoka-shi-2024
- 利用規約: PLATEAU サイトポリシー https://www.mlit.go.jp/plateau/site-policy/ （CC BY 4.0 互換）

## 国土地理院（地盤標高）

- 出典：国土地理院 標高タイル（DEM5A / DEM5B / DEM5C / DEM10B）を加工して作成
- https://maps.gsi.go.jp/development/ichiran.html
- 利用規約: 国土地理院コンテンツ利用規約 https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html （CC BY 4.0 互換）

## フォント

- DotGothic16 © The DotGothic16 Project Authors — SIL Open Font License 1.1 https://openfontlicense.org/
