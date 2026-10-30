import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import 'course.dart';
import 'game.dart';

/// 時間帯ごとの配色。
class Palette {
  const Palette({
    required this.skyTop,
    required this.skyBottom,
    required this.fog,
    required this.mountain,
    required this.skyline,
    required this.ground1,
    required this.ground2,
    required this.road1,
    required this.road2,
    required this.line,
    required this.barrier,
    required this.barrierTop,
    required this.deck,
    required this.light,
    required this.buildingLight,
    required this.night,
  });

  final Color skyTop, skyBottom, fog, mountain, skyline;
  final Color ground1, ground2, road1, road2, line;
  final Color barrier, barrierTop, deck;
  final Color light;

  /// 建物の明るさ倍率。
  final double buildingLight;
  final bool night;

  static const day = Palette(
    skyTop: Color(0xFF2E6FD8),
    skyBottom: Color(0xFFB8E0FF),
    fog: Color(0xFFC6E2F5),
    mountain: Color(0xFF6E9AB8),
    skyline: Color(0xFF94B4CC),
    ground1: Color(0xFF7D8C68),
    ground2: Color(0xFF75845F),
    road1: Color(0xFF5E5F68),
    road2: Color(0xFF595A63),
    line: Color(0xFFF2F2F2),
    barrier: Color(0xFFC9C8BE),
    barrierTop: Color(0xFFE6E4DA),
    deck: Color(0xFF8C8D94),
    light: Color(0xFFFFF4C0),
    buildingLight: 1.0,
    night: false,
  );

  static const evening = Palette(
    skyTop: Color(0xFF2B2160),
    skyBottom: Color(0xFFFF9858),
    fog: Color(0xFFE0866A),
    mountain: Color(0xFF6B3E68),
    skyline: Color(0xFF8C5070),
    ground1: Color(0xFF6A5E58),
    ground2: Color(0xFF645852),
    road1: Color(0xFF4E4A55),
    road2: Color(0xFF4A4651),
    line: Color(0xFFF6E2C8),
    barrier: Color(0xFFC2A898),
    barrierTop: Color(0xFFE0C2A8),
    deck: Color(0xFF7A6A72),
    light: Color(0xFFFFD080),
    buildingLight: 0.8,
    night: false,
  );

  static const nightPalette = Palette(
    skyTop: Color(0xFF03041A),
    skyBottom: Color(0xFF1E2A5A),
    fog: Color(0xFF151C40),
    mountain: Color(0xFF0C1030),
    skyline: Color(0xFF151B44),
    ground1: Color(0xFF15182A),
    ground2: Color(0xFF131626),
    road1: Color(0xFF2A2A34),
    road2: Color(0xFF282831),
    line: Color(0xFFB8B8B0),
    barrier: Color(0xFF5A5A62),
    barrierTop: Color(0xFF6E6E74),
    deck: Color(0xFF2A2C36),
    light: Color(0xFFFFC060),
    buildingLight: 0.28,
    night: true,
  );

  static Palette of(DayTime t) => switch (t) {
        DayTime.day => day,
        DayTime.evening => evening,
        DayTime.night => nightPalette,
      };
}

/// OutRun 風の擬似3D描画。セグメントを奥から手前へ順に描く (画家のアルゴリズム)。
class RoadRenderer {
  RoadRenderer(this.course);

  final Course course;

  static const int drawDistance = 230;
  static const int buildingDistance = 170;
  static const double fovDeg = 100;
  static final double camDepth = 1 / math.tan(fovDeg / 2 * math.pi / 180);

  final _ex = Float64List(drawDistance + 2);
  final _ez = Float64List(drawDistance + 2);
  final _ey = Float64List(drawDistance + 2);
  final _eg = Float64List(drawDistance + 2);
  final _es = Float64List(drawDistance + 2);
  final _paint = Paint()..isAntiAlias = false;
  final _path = Path();

  late double _w, _h, _hy, _camX, _camY;
  late Palette _p;

  double _sx(int k, double lat) => _w / 2 + (_ex[k] + lat - _camX) * _es[k] * _w / 2;
  double _sy(int k, double wy) => _hy - (wy - _camY) * _es[k] * _w / 2;

  Color _fogged(Color c, double f) => f <= 0 ? c : Color.lerp(c, _p.fog, f)!;

  void _quad(Canvas c, double x1, double y1, double x2, double y2, double x3,
      double y3, double x4, double y4, Color color) {
    _path
      ..reset()
      ..moveTo(x1, y1)
      ..lineTo(x2, y2)
      ..lineTo(x3, y3)
      ..lineTo(x4, y4)
      ..close();
    _paint.color = color;
    canvasDrawPath(c);
  }

  void canvasDrawPath(Canvas c) => c.drawPath(_path, _paint);

  void _rect(Canvas c, double l, double t, double r, double b, Color color) {
    _paint.color = color;
    c.drawRect(Rect.fromLTRB(l, t, r, b), _paint);
  }

  void render(Canvas canvas, Game g, double w, double h) {
    _w = w;
    _h = h;
    _hy = h * 0.46;
    _p = Palette.of(g.timeOfDay);
    final cs = course.segmentLength;
    final pos = g.position;
    final base = (pos / cs).floor();
    final basePct = (pos - base * cs) / cs;
    final inTunnel = course.isTunnel(pos);

    // 自車のいる路面の高さにカメラを合わせる (車体が路面に沈まないように)。
    _camY = math.max(course.elevationAt(pos), course.elevationAt(g.playerS)) +
        Game.cameraHeight;
    _camX = g.playerX;

    // 各セグメント境界 (edge) の位置を求める。
    var x = 0.0;
    var dx = -course.curve[course.segIndex(base)] * cs * g.curveScale * basePct;
    for (var k = 0; k <= drawDistance + 1; k++) {
      final s = course.segIndex(base + k);
      _ez[k] = (base + k) * cs - pos;
      _ex[k] = x;
      _ey[k] = course.z[s];
      _eg[k] = course.ground[s];
      _es[k] = camDepth / math.max(_ez[k], 0.6);
      x += dx;
      dx += course.curve[s] * cs * g.curveScale;
    }

    _drawBackground(canvas, g);

    // 一般車をセグメントごとに振り分ける。
    final carsBySeg = <int, List<(TrafficCar, double)>>{};
    for (final t in g.traffic) {
      final z = course.wrap(t.s - pos);
      if (z < 1 || z > drawDistance * cs) continue;
      final k = ((pos + z) / cs).floor() - base;
      (carsBySeg[k] ??= []).add((t, z));
    }

    final maxDepth = drawDistance * cs;
    for (var k = drawDistance - 1; k >= 0; k--) {
      final s = course.segIndex(base + k);
      final f = math.pow(((_ez[k] - 250) / (maxDepth - 250)).clamp(0.0, 1.0), 1.3).toDouble();
      final tunnel = course.tunnel[s] == 1;
      final stripe = ((base + k) ~/ 3).isEven;

      if (!tunnel) {
        // 地面 (高架の下に広がる街の地面)
        final gy = _sy(k + 1, _eg[k + 1]);
        if (gy < h) {
          _rect(canvas, 0, math.max(gy, 0), w, h,
              _fogged(stripe ? _p.ground1 : _p.ground2, f));
        }
        if (k < buildingDistance) _drawBuildings(canvas, s, k, f);
        _drawSupports(canvas, base + k, k, f);
        if (course.tunnel[course.segIndex(base + k + 1)] == 1) {
          _drawPortal(canvas, k + 1, f);
        }
      } else {
        _drawTunnel(canvas, base + k, k, f);
      }

      _drawRoad(canvas, base + k, k, f, tunnel);
      if (!tunnel) _drawBarriers(canvas, base + k, k, f);
      if (!tunnel && (base + k) % 5 == 0) _drawLamp(canvas, k, f);

      final cars = carsBySeg[k];
      if (cars != null) {
        cars.sort((a, b) => b.$2.compareTo(a.$2));
        for (final (car, z) in cars) {
          _drawTrafficCar(canvas, car, z, k, f, tunnel);
        }
      }
    }

    _drawPlayer(canvas, g, inTunnel);
  }

  // ---- 背景 ----

  void _drawBackground(Canvas c, Game g) {
    final w = _w, h = _h, hy = _hy;
    final grad = ui.Gradient.linear(
        Offset(0, 0), Offset(0, hy + 4), [_p.skyTop, _p.skyBottom]);
    c.drawRect(Rect.fromLTRB(0, 0, w, hy + 4), Paint()..shader = grad);
    _rect(c, 0, hy, w, h, _p.ground1);

    final heading = course.headingAt(g.position);
    // 山並み (南の脊振山地のあたりを高く) と遠景のビル群。視点の方位で横に流れる。
    final mountain = Path()..moveTo(0, hy);
    final skyline = Path()..moveTo(0, hy);
    for (var px = 0.0; px <= w + 2; px += 2) {
      final ang = heading +
          math.atan((px - w / 2) / (w / 2) / camDepth) * 180 / math.pi;
      final r = ang * math.pi / 180;
      final south = math.max(0, math.cos(r - math.pi * 1.08));
      final mh = (6 + 10 * south * south) +
          4 * math.sin(r * 5) +
          3 * math.sin(r * 11 + 1) +
          1.5 * math.sin(r * 23);
      mountain.lineTo(px, hy - mh * h / 270);
      final cell = (ang * 3).floor();
      final hash = ((cell * 73856093) ^ (cell * 19349663)) & 0xff;
      final sh = hash < 90 ? 0.0 : (hash % 9) + 1.0;
      skyline.lineTo(px, hy - sh * h / 270);
    }
    mountain
      ..lineTo(w, hy)
      ..close();
    skyline
      ..lineTo(w, hy)
      ..close();
    c.drawPath(mountain, Paint()..color = _p.mountain);
    c.drawPath(skyline, Paint()..color = _p.skyline);
    if (_p.night) {
      final rnd = math.Random(3);
      final dot = Paint()..color = const Color(0xFFFFE6A0);
      for (var i = 0; i < 40; i++) {
        final px = (rnd.nextDouble() * 1000 - heading * 4) % w;
        c.drawRect(Rect.fromLTWH(px, hy - rnd.nextDouble() * 6 * h / 270, 1, 1), dot);
      }
    }

    // 福岡タワーなど、遠くからも見える名所を実際の方角に描く。
    final me = course.mapPosition(g.position);
    for (final l in course.sights) {
      if (l.height < 100) continue;
      final d = (l.pos - me).distance;
      if (d < 400) continue;
      final bearing = math.atan2(l.pos.dx - me.dx, l.pos.dy - me.dy) * 180 / math.pi;
      var rel = bearing - heading;
      rel = (rel + 540) % 360 - 180;
      if (rel.abs() > 58) continue;
      final px = w / 2 + math.tan(rel * math.pi / 180) * camDepth * w / 2;
      final sc = camDepth / d * w / 2;
      final baseY = hy + (_camY - 5) * sc;
      // 福岡タワーは全高 234m。データ上の高さが低い場合も見栄えのため塔として描く。
      final towerH = l.name.contains('タワー') ? 234.0 : l.height;
      final top = baseY - towerH * sc;
      final col = Color.lerp(_p.skyline, _p.mountain, 0.5)!;
      final half = math.max(1.0, 12 * sc);
      if (!l.name.contains('タワー')) {
        _rect(c, px - half * 2, top, px + half * 2, baseY, col);
        continue;
      }
      _quad(c, px - half, baseY, px + half, baseY, px + half * 0.35, top,
          px - half * 0.35, top, col);
      {
        _rect(c, px - half * 0.9, top + towerH * sc * 0.18, px + half * 0.9,
            top + towerH * sc * 0.24, col);
        _rect(c, px - 0.5, top - 30 * sc, px + 0.5, top, col);
      }
    }
  }

  // ---- 道路まわり ----

  void _drawRoad(Canvas c, int i, int k, double f, bool tunnel) {
    const hw = Game.roadHalfWidth;
    final y1 = _sy(k, _ey[k]), y2 = _sy(k + 1, _ey[k + 1]);
    if (y2 >= y1 && y1 < 0) return;
    final alt = (i ~/ 2).isEven;
    var road = alt ? _p.road1 : _p.road2;
    if (tunnel) road = Color.lerp(road, const Color(0xFF6A4A20), 0.35)!;
    _quad(c, _sx(k, -hw), y1, _sx(k, hw), y1, _sx(k + 1, hw), y2,
        _sx(k + 1, -hw), y2, _fogged(road, f));

    final line = _fogged(tunnel ? const Color(0xFFE8D8A0) : _p.line, f);
    void stripe(double a, double b) =>
        _quad(c, _sx(k, a), y1, _sx(k, b), y1, _sx(k + 1, b), y2, _sx(k + 1, a), y2, line);
    // 外側線
    stripe(-hw + 0.9, -hw + 1.1);
    stripe(hw - 1.1, hw - 0.9);
    // 車線境界 (破線)
    if (i % 4 < 2) stripe(-0.08, 0.08);
  }

  void _drawBarriers(Canvas c, int i, int k, double f) {
    const hw = Game.roadHalfWidth;
    const bh = 1.1;
    final shade = (i ~/ 2).isEven ? 1.0 : 0.94;
    final face = _fogged(_scale(_p.barrier, shade), f);
    final top = _fogged(_p.barrierTop, f);
    for (final side in const [-1.0, 1.0]) {
      final l = side * hw;
      final l2 = side * (hw + 0.4);
      final xn = _sx(k, l), xf = _sx(k + 1, l);
      final yb1 = _sy(k, _ey[k]), yb2 = _sy(k + 1, _ey[k + 1]);
      final yt1 = _sy(k, _ey[k] + bh), yt2 = _sy(k + 1, _ey[k + 1] + bh);
      _quad(c, xn, yb1, xn, yt1, xf, yt2, xf, yb2, face);
      _quad(c, xn, yt1, _sx(k, l2), yt1, _sx(k + 1, l2), yt2, xf, yt2, top);
    }
  }

  void _drawSupports(Canvas c, int i, int k, double f) {
    final lift = _ey[k] - _eg[k];
    if (lift < 3.5) return;
    const hw = Game.roadHalfWidth + 0.4;
    final deck = _fogged(_p.deck, f);
    // 桁の側面
    for (final side in const [-1.0, 1.0]) {
      final l = side * hw;
      _quad(c, _sx(k, l), _sy(k, _ey[k]), _sx(k + 1, l), _sy(k + 1, _ey[k + 1]),
          _sx(k + 1, l), _sy(k + 1, _ey[k + 1] - 2.0), _sx(k, l),
          _sy(k, _ey[k] - 2.0), _scale(deck, 0.85));
    }
    // 橋脚 (40m ごと)
    if (i % 4 == 0) {
      final pillar = _fogged(_scale(_p.deck, 1.1), f);
      _rect(c, _sx(k, -1.4), _sy(k, _ey[k] - 2.0), _sx(k, 1.4), _sy(k, _eg[k]), pillar);
    }
  }

  void _drawLamp(Canvas c, int k, double f) {
    const hw = Game.roadHalfWidth + 0.2;
    final x = _sx(k, -hw);
    final yb = _sy(k, _ey[k] + 1.1);
    final yt = _sy(k, _ey[k] + 9);
    final pw = math.max(1.0, 0.25 * _es[k] * _w / 2);
    final pole = _fogged(const Color(0xFF8A9098), f);
    _rect(c, x - pw / 2, yt, x + pw / 2, yb, pole);
    final ax = _sx(k, -hw + 1.8);
    _rect(c, x, yt, ax, yt + pw, pole);
    final lampW = math.max(1.0, 0.7 * _es[k] * _w / 2);
    _rect(c, ax - lampW / 2, yt, ax + lampW / 2, yt + pw * 1.5,
        _fogged(_p.night ? _p.light : const Color(0xFFDDE2E8), f * 0.5));
    if (_p.night && f < 0.8) {
      final r = 1.6 * _es[k] * _w / 2;
      c.drawCircle(Offset(ax, yt + pw), r,
          Paint()..color = _p.light.withValues(alpha: 0.12 * (1 - f)));
    }
  }

  void _drawPortal(Canvas c, int k, double f) {
    const hw = Game.roadHalfWidth + 0.5;
    final ey = _ey[k];
    final color = _fogged(const Color(0xFF9A988E), f);
    final hill = _fogged(Color.lerp(_p.ground1, const Color(0xFF3E6E3A), 0.6)!, f);
    // 山の斜面と坑口の壁面
    _quad(c, _sx(k, -120), _sy(k, ey - 4), _sx(k, -60), _sy(k, ey + 26),
        _sx(k, 60), _sy(k, ey + 26), _sx(k, 120), _sy(k, ey - 4), hill);
    _rect(c, _sx(k, -24), _sy(k, ey + 12), _sx(k, -hw), _sy(k, ey - 1), color);
    _rect(c, _sx(k, hw), _sy(k, ey + 12), _sx(k, 24), _sy(k, ey - 1), color);
    _rect(c, _sx(k, -hw), _sy(k, ey + 12), _sx(k, hw), _sy(k, ey + 7), color);
    _rect(c, _sx(k, -hw), _sy(k, ey + 7), _sx(k, hw), _sy(k, ey - 1),
        _fogged(const Color(0xFF14110C), f));
  }

  void _drawTunnel(Canvas c, int i, int k, double f) {
    const hw = Game.roadHalfWidth + 0.5;
    final alt = (i ~/ 2).isEven;
    final wall = Color(alt ? 0xFF6E6250 : 0xFF665A49);
    final ceil = Color(alt ? 0xFF3A342C : 0xFF36302A);
    final y0 = _ey[k], y1 = _ey[k + 1];
    // 路肩 (壁と車道のすき間)
    _quad(c, _sx(k, -hw), _sy(k, y0), _sx(k, hw), _sy(k, y0), _sx(k + 1, hw),
        _sy(k + 1, y1), _sx(k + 1, -hw), _sy(k + 1, y1), const Color(0xFF4A4038));
    for (final side in const [-1.0, 1.0]) {
      final l = side * hw;
      _quad(c, _sx(k, l), _sy(k, y0), _sx(k, l), _sy(k, y0 + 5), _sx(k + 1, l),
          _sy(k + 1, y1 + 5), _sx(k + 1, l), _sy(k + 1, y1), wall);
      _quad(c, _sx(k, l), _sy(k, y0 + 5), _sx(k, 0), _sy(k, y0 + 7.2),
          _sx(k + 1, 0), _sy(k + 1, y1 + 7.2), _sx(k + 1, l), _sy(k + 1, y1 + 5), ceil);
    }
    // 照明 (オレンジのナトリウム灯)
    if (i % 2 == 0) {
      for (final side in const [-1.0, 1.0]) {
        final a = side * (hw - 0.3), b = side * (hw - 1.6);
        _quad(c, _sx(k, a), _sy(k, y0 + 5.4), _sx(k, b), _sy(k, y0 + 5.9),
            _sx(k, b), _sy(k, y0 + 6.1), _sx(k, a), _sy(k, y0 + 5.6),
            const Color(0xFFFFB040));
      }
    }
  }

  // ---- 建物 ----

  static const _kindColors = [
    Color(0xFFD8C8A8), // 戸建て
    Color(0xFFE2DED2), // 集合住宅
    Color(0xFF8FB4D0), // 商業・オフィス
    Color(0xFF9AA4AE), // 倉庫・工場
    Color(0xFFD0B490), // 公共
    Color(0xFFBEBAB2), // 不明
  ];
  static const _roofColors = [
    Color(0xFF7A4A3A),
    Color(0xFF9A9A98),
    Color(0xFF7D8A96),
    Color(0xFF8A9092),
    Color(0xFF8E7A68),
    Color(0xFF8C8884),
  ];

  void _drawBuildings(Canvas c, int s, int k, double f) {
    final list = course.buildingsBySeg[s];
    if (list.isEmpty || _ez[k] < 2) return;
    for (final b in list) {
      final int kb = math.min(k + math.max(1, (b.depth / course.segmentLength).round()),
          drawDistance + 1);
      final xl = b.offset - b.width / 2, xr = b.offset + b.width / 2;
      final fx1 = _sx(k, xl), fx2 = _sx(k, xr);
      final bx1 = _sx(kb, xl), bx2 = _sx(kb, xr);
      if (math.max(fx2, bx2) < 0 || math.min(fx1, bx1) > _w) continue;
      final g0 = _eg[k];
      final top = g0 + b.height;
      final fyB = _sy(k, g0), fyT = _sy(k, top);
      final byB = _sy(kb, g0), byT = _sy(kb, top);
      if (fyT > _h && byT > _h) continue;

      final light = _p.buildingLight * (0.85 + 0.3 * b.shade);
      final baseCol = _scale(_kindColors[b.kind], light);
      if (top < _camY) {
        _quad(c, fx1, fyT, fx2, fyT, bx2, byT, bx1, byT,
            _fogged(_scale(_roofColors[b.kind], light * 1.05), f));
      }
      if (b.offset > 0) {
        _quad(c, fx1, fyB, fx1, fyT, bx1, byT, bx1, byB, _fogged(_scale(baseCol, 0.72), f));
      } else {
        _quad(c, fx2, fyB, fx2, fyT, bx2, byT, bx2, byB, _fogged(_scale(baseCol, 0.72), f));
      }
      _rect(c, fx1, fyT, fx2, fyB, _fogged(baseCol, f));

      // 窓 (階ごとの帯)
      final floorPx = 3.2 * _es[k] * _w / 2;
      if (floorPx >= 3 && b.height >= 6 && fx2 - fx1 > 4) {
        final floors = (b.height / 3.2).floor();
        final win = _p.night ? const Color(0xFFFFD27A) : _scale(const Color(0xFF4A5A70), 0.9 + 0.2 * b.shade);
        final pad = math.max(1.0, (fx2 - fx1) * 0.08);
        for (var fl = 0; fl < floors; fl++) {
          if (_p.night && ((b.seg * 31 + fl * 17 + (b.offset * 7).round()) % 5 < 2)) continue;
          final yy = fyB - (fl + 0.55) * floorPx;
          _rect(c, fx1 + pad, yy - floorPx * 0.35, fx2 - pad, yy, _fogged(win, f));
        }
      }
    }
  }

  // ---- 車 ----

  static Color _scale(Color c, double k) => Color.fromARGB(
        (c.a * 255).round(),
        (c.r * 255 * k).clamp(0.0, 255.0).round(),
        (c.g * 255 * k).clamp(0.0, 255.0).round(),
        (c.b * 255 * k).clamp(0.0, 255.0).round(),
      );

  void _drawTrafficCar(Canvas c, TrafficCar car, double z, int k, double f, bool tunnel) {
    final t = ((z - _ez[k]) / course.segmentLength).clamp(0.0, 1.0);
    final cx = _ex[k] + (_ex[k + 1] - _ex[k]) * t;
    final cy = _ey[k] + (_ey[k + 1] - _ey[k]) * t;
    final sc = camDepth / z * _w / 2;
    final x = _w / 2 + (cx + car.x - _camX) * sc;
    final y = _hy - (cy - _camY) * sc;
    final hw = car.width / 2 * sc, hh = car.height * sc;
    if (x + hw < 0 || x - hw > _w || hh < 0.8) return;
    final body = _fogged(Color(car.color), f);
    final dark = _fogged(_scale(Color(car.color), 0.6), f);
    // 影とタイヤ
    _rect(c, x - hw * 1.05, y - hh * 0.12, x + hw * 1.05, y + 0.5, _fogged(const Color(0xFF202024), f));
    if (car.kind == 0) {
      _rect(c, x - hw, y - hh * 0.62, x + hw, y - hh * 0.1, body);
      _quad(c, x - hw * 0.82, y - hh * 0.62, x - hw * 0.62, y - hh, x + hw * 0.62,
          y - hh, x + hw * 0.82, y - hh * 0.62, dark);
      _rect(c, x - hw * 0.6, y - hh * 0.92, x + hw * 0.6, y - hh * 0.68,
          _fogged(const Color(0xFF283848), f));
    } else {
      _rect(c, x - hw, y - hh, x + hw, y - hh * 0.1, body);
      _rect(c, x - hw * 0.9, y - hh * 0.95, x + hw * 0.9, y - hh * 0.2, dark);
      if (car.kind == 2) {
        _rect(c, x - hw * 0.8, y - hh * 0.9, x + hw * 0.8, y - hh * 0.62,
            _fogged(const Color(0xFF283848), f));
      }
    }
    // テールランプ
    final lampOn = _p.night || tunnel;
    final lamp = _fogged(lampOn ? const Color(0xFFFF3030) : const Color(0xFFB02020), f * 0.6);
    final ly = y - hh * (car.kind == 0 ? 0.45 : 0.25);
    _rect(c, x - hw * 0.95, ly - hh * 0.1, x - hw * 0.6, ly, lamp);
    _rect(c, x + hw * 0.6, ly - hh * 0.1, x + hw * 0.95, ly, lamp);
  }

  void _drawPlayer(Canvas c, Game g, bool tunnel) {
    final sc = camDepth / Game.carAhead * _w / 2;
    final roadY = _hy + Game.cameraHeight * sc;
    final shake = g.speed > 1
        ? math.sin(g.totalTime * 40) * 0.6 * (g.speed / Game.maxSpeed) + g.bump * math.sin(g.totalTime * 70) * 2
        : 0.0;
    final x = _w / 2;
    final y = roadY + shake;
    final hw = 0.98 * sc;
    final hh = 1.25 * sc;
    final lean = g.steer * hw * 0.12;

    const red = Color(0xFFD82828);
    const redDark = Color(0xFF8E1414);
    _rect(c, x - hw * 1.08, y - hh * 0.1, x + hw * 1.08, y + 2, const Color(0x99000000));
    // タイヤ
    _rect(c, x - hw, y - hh * 0.3, x - hw * 0.68, y, const Color(0xFF151515));
    _rect(c, x + hw * 0.68, y - hh * 0.3, x + hw, y, const Color(0xFF151515));
    // ボディ
    _quad(c, x - hw * 1.02, y - hh * 0.2, x - hw * 0.98, y - hh * 0.6,
        x + hw * 0.98, y - hh * 0.6, x + hw * 1.02, y - hh * 0.2, red);
    _rect(c, x - hw * 0.9, y - hh * 0.28, x + hw * 0.9, y - hh * 0.18, redDark);
    // キャビン
    _quad(c, x - hw * 0.8 + lean, y - hh * 0.6, x - hw * 0.6 + lean, y - hh,
        x + hw * 0.6 + lean, y - hh, x + hw * 0.8 + lean, y - hh * 0.6, redDark);
    _quad(c, x - hw * 0.7 + lean, y - hh * 0.62, x - hw * 0.55 + lean, y - hh * 0.93,
        x + hw * 0.55 + lean, y - hh * 0.93, x + hw * 0.7 + lean, y - hh * 0.62,
        const Color(0xFF1A2A40));
    // リアウイング
    _rect(c, x - hw * 0.95, y - hh * 0.72, x + hw * 0.95, y - hh * 0.64, const Color(0xFF202020));
    // テールランプとナンバー
    final braking = g.controls.brake;
    final lamp = braking ? const Color(0xFFFF6060) : const Color(0xFFC01818);
    _rect(c, x - hw * 0.92, y - hh * 0.52, x - hw * 0.55, y - hh * 0.4, lamp);
    _rect(c, x + hw * 0.55, y - hh * 0.52, x + hw * 0.92, y - hh * 0.4, lamp);
    if (braking || _p.night || tunnel) {
      final glow = Paint()..color = const Color(0x55FF3020);
      c.drawCircle(Offset(x - hw * 0.73, y - hh * 0.46), hh * 0.2, glow);
      c.drawCircle(Offset(x + hw * 0.73, y - hh * 0.46), hh * 0.2, glow);
    }
    _rect(c, x - hw * 0.2, y - hh * 0.5, x + hw * 0.2, y - hh * 0.36, const Color(0xFFF0F0E0));
  }
}
