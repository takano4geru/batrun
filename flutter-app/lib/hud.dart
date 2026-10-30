import 'package:flutter/material.dart';

import 'course.dart';
import 'game.dart';

String _fmtTime(double t) {
  final m = t ~/ 60;
  final s = t - m * 60;
  return "$m'${s.toStringAsFixed(2).padLeft(5, '0')}";
}

/// 速度・ラップ・次のランプ・ミニマップなどの表示と、タッチ操作ボタン。
class Hud extends StatelessWidget {
  const Hud({super.key, required this.game, required this.unit});

  final Game game;
  final double unit;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: game,
      builder: (context, _) {
        final u = unit;
        final course = game.course;
        final s = game.playerS;
        final (ramp, rampDist) = course.nextRamp(s);
        final sight = course.nearbySight(s);
        final z = course.elevationAt(s);
        final lift = z - course.groundAt(s);
        final where = course.isTunnel(s)
            ? 'トンネル'
            : lift > 3.5
                ? '高架 ${lift.toStringAsFixed(0)}m'
                : '地上';

        TextStyle st(double size, [Color color = Colors.white]) => TextStyle(
              fontFamily: 'DotGothic16',
              fontSize: size * u,
              color: color,
              height: 1.1,
              shadows: [Shadow(offset: Offset(u, u), color: Colors.black)],
            );

        return Stack(children: [
          // 左上: 速度とラップ
          Positioned(
            left: 8 * u,
            top: 6 * u,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(crossAxisAlignment: CrossAxisAlignment.baseline, textBaseline: TextBaseline.alphabetic, children: [
                Text(game.speedKmh.toStringAsFixed(0).padLeft(3), style: st(26, const Color(0xFFFFE040))),
                SizedBox(width: 3 * u),
                Text('km/h', style: st(10)),
              ]),
              Text('LAP ${game.lap}  ${_fmtTime(game.lapTime)}', style: st(10)),
              if (game.bestLap != null) Text('BEST ${_fmtTime(game.bestLap!)}', style: st(9, const Color(0xFF80FFA0))),
            ]),
          ),
          // 上中央: 次のランプと名所
          Positioned(
            left: 0,
            right: 0,
            top: 6 * u,
            child: Column(children: [
              _panel(u, Text('次のランプ  ${ramp.name}  ${(rampDist / 1000).toStringAsFixed(1)}km', style: st(9))),
              if (sight != null)
                Padding(
                  padding: EdgeInsets.only(top: 3 * u),
                  child: _panel(
                    u,
                    Text(sight.$2 > 0 ? 'まもなく ${sight.$1.name}' : '${sight.$1.name} 付近', style: st(9, const Color(0xFFFFD080))),
                  ),
                ),
            ]),
          ),
          // 右上: ミニマップ
          Positioned(
            right: 6 * u,
            top: 6 * u,
            width: 84 * u,
            height: 84 * u,
            child: _panel(u, CustomPaint(painter: MiniMapPainter(course, s)), pad: 3),
          ),
          // 左下: 位置
          Positioned(
            left: 8 * u,
            bottom: 18 * u,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${(s / 1000).toStringAsFixed(2)} / ${(course.length / 1000).toStringAsFixed(2)} km', style: st(9)),
              Text('$where  標高${z.toStringAsFixed(0)}m', style: st(9)),
              SizedBox(height: 2 * u),
              Container(
                width: 90 * u,
                height: 3 * u,
                color: Colors.white24,
                alignment: Alignment.centerLeft,
                child: FractionallySizedBox(widthFactor: s / course.length, child: Container(color: const Color(0xFFFFE040))),
              ),
            ]),
          ),
          // 下端: 出典
          Positioned(
            left: 0,
            right: 0,
            bottom: 2 * u,
            child: Text(
              '地図データ © OpenStreetMap contributors (ODbL) / Overture Maps Foundation\n'
              '国土交通省 Project PLATEAU（福岡市 3D都市モデル）・国土地理院 標高タイルを加工して作成',
              textAlign: TextAlign.center,
              style: st(6, Colors.white70),
            ),
          ),
          if (game.started) ..._touchControls(u),
          if (!game.started) _title(u, st),
          if (game.paused)
            Center(child: _panel(u, Text('PAUSE', style: st(20)), pad: 8)),
        ]);
      },
    );
  }

  Widget _panel(double u, Widget child, {double pad = 4}) => Container(
        padding: EdgeInsets.symmetric(horizontal: pad * 1.5 * u, vertical: pad * 0.6 * u),
        decoration: BoxDecoration(
          color: const Color(0x99000020),
          border: Border.all(color: Colors.white54, width: u),
        ),
        child: child,
      );

  Widget _title(double u, TextStyle Function(double, [Color]) st) {
    return Positioned.fill(
      child: GestureDetector(
        onTap: game.start,
        child: Container(
          color: const Color(0x66000000),
          alignment: Alignment.center,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text('FUKUOKA EXPRESSWAY', style: st(22, const Color(0xFFFFE040))),
            Text('福岡都市高速 環状線ドライブ', style: st(14)),
            SizedBox(height: 4 * u),
            Text('実データの線形・標高・沿線建物で一周 34.7km', style: st(8, Colors.white70)),
            SizedBox(height: 12 * u),
            Text('ENTER / タップでスタート', style: st(11)),
            SizedBox(height: 10 * u),
            Text('↑ アクセル  ↓ ブレーキ  ← → ハンドル\nT 時間帯  P ドット表示  C カーブ強調  ESC ポーズ',
                textAlign: TextAlign.center, style: st(8, Colors.white70)),
          ]),
        ),
      ),
    );
  }

  List<Widget> _touchControls(double u) {
    final c = game.controls;
    return [
      Positioned(
        left: 8 * u,
        bottom: 52 * u,
        child: Row(children: [
          HoldButton(label: '◀', unit: u, onChanged: (v) => c.left = v),
          SizedBox(width: 6 * u),
          HoldButton(label: '▶', unit: u, onChanged: (v) => c.right = v),
        ]),
      ),
      Positioned(
        right: 8 * u,
        bottom: 18 * u,
        child: Row(children: [
          HoldButton(label: 'BRK', unit: u, onChanged: (v) => c.brake = v),
          SizedBox(width: 6 * u),
          HoldButton(label: 'ACC', unit: u, onChanged: (v) => c.accel = v, color: const Color(0x8840C040)),
        ]),
      ),
      Positioned(
        right: 8 * u,
        top: 96 * u,
        child: Column(children: [
          _smallButton(u, '時間帯', game.cycleDayTime),
          SizedBox(height: 3 * u),
          _smallButton(u, 'ドット', game.togglePixelated),
        ]),
      ),
    ];
  }

  Widget _smallButton(double u, String label, VoidCallback onTap) => GestureDetector(
        onTap: onTap,
        child: Container(
          width: 40 * u,
          padding: EdgeInsets.symmetric(vertical: 2 * u),
          alignment: Alignment.center,
          decoration: BoxDecoration(color: const Color(0x66000000), border: Border.all(color: Colors.white38, width: u)),
          child: Text(label, style: TextStyle(fontFamily: 'DotGothic16', fontSize: 7 * u, color: Colors.white70)),
        ),
      );
}

/// 押している間だけ true になるボタン (複数同時押し可)。
class HoldButton extends StatefulWidget {
  const HoldButton({super.key, required this.label, required this.unit, required this.onChanged, this.color = const Color(0x55FFFFFF)});
  final String label;
  final double unit;
  final ValueChanged<bool> onChanged;
  final Color color;

  @override
  State<HoldButton> createState() => _HoldButtonState();
}

class _HoldButtonState extends State<HoldButton> {
  bool _down = false;

  void _set(bool v) {
    if (_down == v) return;
    setState(() => _down = v);
    widget.onChanged(v);
  }

  @override
  Widget build(BuildContext context) {
    final u = widget.unit;
    return Listener(
      onPointerDown: (_) => _set(true),
      onPointerUp: (_) => _set(false),
      onPointerCancel: (_) => _set(false),
      child: Container(
        width: 34 * u,
        height: 34 * u,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: _down ? widget.color.withValues(alpha: 0.8) : widget.color.withValues(alpha: 0.25),
          shape: BoxShape.circle,
          border: Border.all(color: Colors.white38, width: u),
        ),
        child: Text(widget.label, style: TextStyle(fontFamily: 'DotGothic16', fontSize: 10 * u, color: Colors.white)),
      ),
    );
  }
}

/// 環状線の平面形と自車位置 (北が上)。
class MiniMapPainter extends CustomPainter {
  MiniMapPainter(this.course, this.s);
  final Course course;
  final double s;

  @override
  void paint(Canvas canvas, Size size) {
    final pts = course.mapPoints;
    var minX = pts.first.dx, maxX = minX, minY = pts.first.dy, maxY = minY;
    for (final p in pts) {
      if (p.dx < minX) minX = p.dx;
      if (p.dx > maxX) maxX = p.dx;
      if (p.dy < minY) minY = p.dy;
      if (p.dy > maxY) maxY = p.dy;
    }
    final scale = (size.width / (maxX - minX)) < (size.height / (maxY - minY))
        ? size.width / (maxX - minX)
        : size.height / (maxY - minY);
    final ox = (size.width - (maxX - minX) * scale) / 2;
    final oy = (size.height - (maxY - minY) * scale) / 2;
    Offset tr(Offset p) => Offset(ox + (p.dx - minX) * scale, oy + (maxY - p.dy) * scale);

    final path = Path()..moveTo(tr(pts.first).dx, tr(pts.first).dy);
    for (final p in pts.skip(1)) {
      final q = tr(p);
      path.lineTo(q.dx, q.dy);
    }
    path.close();
    canvas.drawPath(
        path,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = size.width / 40
          ..color = Colors.white70);
    final me = tr(course.mapPosition(s));
    canvas.drawCircle(me, size.width / 22, Paint()..color = const Color(0xFFFF3030));
    final start = tr(course.mapPosition(0));
    canvas.drawRect(Rect.fromCenter(center: start, width: size.width / 25, height: size.width / 12), Paint()..color = const Color(0xFFFFE040));
  }

  @override
  bool shouldRepaint(covariant MiniMapPainter old) => old.s != s;
}
