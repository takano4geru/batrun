import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/services.dart';

/// 沿線の建物 1 棟分。seg はコース上のセグメント番号、offset は進行方向右が正 [m]。
class Building {
  Building(this.seg, this.offset, this.height, this.width, this.depth,
      this.kind, this.shade);

  final int seg;
  final double offset;
  final double height;
  final double width;
  final double depth;
  final int kind;

  /// 色のばらつき用 (0..1)。
  final double shade;
}

class Landmark {
  Landmark(this.s, this.name,
      {this.isRamp = true, this.height = 0, this.pos = Offset.zero});
  final double s;
  final Offset pos;
  final String name;
  final bool isRamp;
  final double height;
}

/// tool/build_assets.py が出力した assets/course_data.json を保持する。
class Course {
  Course._({
    required this.name,
    required this.length,
    required this.segmentLength,
    required this.attribution,
    required this.curve,
    required this.z,
    required this.ground,
    required this.heading,
    required this.level,
    required this.tunnel,
    required this.mapPoints,
    required this.ramps,
    required this.sights,
    required this.buildingsBySeg,
  });

  final String name;
  final double length;
  final double segmentLength;
  final String attribution;
  final Float64List curve;
  final Float64List z;
  final Float64List ground;
  final Float64List heading;
  final Int8List level;
  final Uint8List tunnel;
  final List<Offset> mapPoints;
  final List<Landmark> ramps;
  final List<Landmark> sights;

  /// セグメントごとの建物。道路から遠い順 (描画順) に並ぶ。
  final List<List<Building>> buildingsBySeg;

  int get segmentCount => curve.length;

  static Future<Course> load() async {
    final raw = await rootBundle.loadString('assets/course_data.json');
    final j = jsonDecode(raw) as Map<String, dynamic>;
    Float64List f(String k) => Float64List.fromList(
        (j[k] as List).map((e) => (e as num).toDouble()).toList());

    final curve = f('curve');
    final n = curve.length;
    final bySeg = List.generate(n, (_) => <Building>[]);
    final rnd = math.Random(42);
    for (final b in j['buildings'] as List) {
      final r = b as List;
      final seg = r[0] as int;
      bySeg[seg].add(Building(
        seg,
        (r[1] as num).toDouble(),
        (r[2] as num).toDouble(),
        (r[3] as num).toDouble(),
        (r[4] as num).toDouble(),
        r[5] as int,
        rnd.nextDouble(),
      ));
    }
    for (final l in bySeg) {
      l.sort((a, b) => b.offset.abs().compareTo(a.offset.abs()));
    }

    return Course._(
      name: j['name'] as String,
      // 周回の継ぎ目でセグメントとずれないよう、長さはセグメント数から決める。
      length: n * (j['segment_length_m'] as num).toDouble(),
      segmentLength: (j['segment_length_m'] as num).toDouble(),
      attribution: j['attribution'] as String,
      curve: curve,
      z: f('z'),
      ground: f('ground'),
      heading: f('heading'),
      level: Int8List.fromList((j['level'] as List).cast<int>()),
      tunnel: Uint8List.fromList((j['tunnel'] as List).cast<int>()),
      mapPoints: [
        for (final p in j['map'] as List)
          Offset((p[0] as num).toDouble(), (p[1] as num).toDouble())
      ],
      ramps: [
        for (final l in j['landmarks'] as List)
          Landmark((l['s'] as num).toDouble(), l['name'] as String)
      ],
      sights: [
        for (final l in j['named_buildings'] as List)
          Landmark((l['s'] as num).toDouble(), l['name'] as String,
              isRamp: false,
              height: (l['height'] as num).toDouble(),
              pos: Offset((l['x'] as num).toDouble(), (l['y'] as num).toDouble())),
        // PLATEAU の建物データに福岡タワーは含まれないので、位置 (OSM 由来) を固定で持つ。
        if (!(j['named_buildings'] as List).any((l) => l['name'] == '福岡タワー'))
          Landmark(30189.1, '福岡タワー',
              isRamp: false, height: 234, pos: const Offset(-4499.0, 368.8)),
      ]..sort((a, b) => a.s.compareTo(b.s)),
      buildingsBySeg: bySeg,
    );
  }

  int segIndex(int i) => ((i % segmentCount) + segmentCount) % segmentCount;

  double wrap(double s) => ((s % length) + length) % length;

  double _lerpArr(Float64List a, double s) {
    final p = wrap(s) / segmentLength;
    final i = p.floor();
    final t = p - i;
    return a[segIndex(i)] * (1 - t) + a[segIndex(i + 1)] * t;
  }

  double elevationAt(double s) => _lerpArr(z, s);
  double groundAt(double s) => _lerpArr(ground, s);

  double headingAt(double s) {
    final p = wrap(s) / segmentLength;
    final i = p.floor();
    final t = p - i;
    final a = heading[segIndex(i)];
    var b = heading[segIndex(i + 1)];
    if (b - a > 180) b -= 360;
    if (a - b > 180) b += 360;
    return a + (b - a) * t;
  }

  bool isTunnel(double s) => tunnel[segIndex((wrap(s) / segmentLength).floor())] == 1;

  int levelAt(double s) => level[segIndex((wrap(s) / segmentLength).floor())];

  /// 地図上の位置 (ローカル平面 [m])。
  Offset mapPosition(double s) {
    final p = wrap(s) / (segmentLength * 5);
    final i = p.floor() % mapPoints.length;
    final t = p - p.floor();
    final a = mapPoints[i];
    final b = mapPoints[(i + 1) % mapPoints.length];
    return Offset.lerp(a, b, t)!;
  }

  /// s より先で最初に現れるランプ (周回をまたぐ)。
  (Landmark, double) nextRamp(double s) {
    final w = wrap(s);
    for (final r in ramps) {
      if (r.s > w + 1) return (r, r.s - w);
    }
    return (ramps.first, ramps.first.s + length - w);
  }

  /// 前後 [range] m 以内にある名所。
  (Landmark, double)? nearbySight(double s, {double range = 600}) {
    final w = wrap(s);
    for (final l in sights) {
      var d = l.s - w;
      if (d > length / 2) d -= length;
      if (d < -length / 2) d += length;
      if (d > -150 && d < range) return (l, d);
    }
    return null;
  }
}
