import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';

import 'course.dart';
import 'game.dart';
import 'hud.dart';
import 'renderer.dart';

void main() {
  runApp(const FukuokaDriveApp());
}

class FukuokaDriveApp extends StatelessWidget {
  const FukuokaDriveApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '福岡都市高速 環状線ドライブ',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        fontFamily: 'DotGothic16',
        scaffoldBackgroundColor: Colors.black,
      ),
      home: const LoadingScreen(),
    );
  }
}

class LoadingScreen extends StatefulWidget {
  const LoadingScreen({super.key});

  @override
  State<LoadingScreen> createState() => _LoadingScreenState();
}

class _LoadingScreenState extends State<LoadingScreen> {
  late final Future<Course> _course = Course.load();

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Course>(
      future: _course,
      builder: (context, snap) {
        if (snap.hasError) {
          return Scaffold(body: Center(child: Text('読み込み失敗: ${snap.error}')));
        }
        if (!snap.hasData) {
          return const Scaffold(body: Center(child: Text('コースデータを読み込み中…')));
        }
        return GameScreen(course: snap.data!);
      },
    );
  }
}

class GameScreen extends StatefulWidget {
  const GameScreen({super.key, required this.course});
  final Course course;

  @override
  State<GameScreen> createState() => _GameScreenState();
}

class _GameScreenState extends State<GameScreen> with SingleTickerProviderStateMixin {
  late final Game game = Game(widget.course);
  late final RoadRenderer renderer = RoadRenderer(widget.course);
  late final Ticker _ticker;
  Duration _last = Duration.zero;
  final _focus = FocusNode();

  @override
  void initState() {
    super.initState();
    _applyUrlOptions();
    _ticker = createTicker((elapsed) {
      final dt = (elapsed - _last).inMicroseconds / 1e6;
      _last = elapsed;
      game.update(dt);
    })
      ..start();
  }

  /// 動作確認用: ?s=29000&tod=night&speed=120&auto=1 のように開始状態を指定できる。
  void _applyUrlOptions() {
    final q = Uri.base.queryParameters;
    final s = double.tryParse(q['s'] ?? '');
    if (s != null) game.position = widget.course.wrap(s);
    final tod = q['tod'];
    if (tod != null) {
      game.timeOfDay = DayTime.values.firstWhere((t) => t.name == tod,
          orElse: () => DayTime.day);
    }
    final v = double.tryParse(q['speed'] ?? '');
    if (v != null) game.speed = v / 3.6;
    if (q['auto'] == '1') {
      game.started = true;
      game.controls.accel = v == null;
    }
    if (q['pixel'] == '0') game.pixelated = false;
  }

  @override
  void dispose() {
    _ticker.dispose();
    _focus.dispose();
    game.dispose();
    super.dispose();
  }

  KeyEventResult _onKey(FocusNode node, KeyEvent e) {
    final keys = HardwareKeyboard.instance.logicalKeysPressed;
    bool any(List<LogicalKeyboardKey> ks) => ks.any(keys.contains);
    final c = game.controls;
    c.left = any([LogicalKeyboardKey.arrowLeft, LogicalKeyboardKey.keyA]);
    c.right = any([LogicalKeyboardKey.arrowRight, LogicalKeyboardKey.keyD]);
    c.accel = any([LogicalKeyboardKey.arrowUp, LogicalKeyboardKey.keyW]);
    c.brake = any([LogicalKeyboardKey.arrowDown, LogicalKeyboardKey.keyS, LogicalKeyboardKey.space]);

    if (e is KeyDownEvent) {
      final k = e.logicalKey;
      if (!game.started && (k == LogicalKeyboardKey.enter || c.accel)) game.start();
      if (k == LogicalKeyboardKey.keyT) game.cycleDayTime();
      if (k == LogicalKeyboardKey.keyP) game.togglePixelated();
      if (k == LogicalKeyboardKey.escape) game.togglePause();
      if (k == LogicalKeyboardKey.keyC) {
        game.curveScale = switch (game.curveScale) { 2.5 => 5.0, 5.0 => 1.0, _ => 2.5 };
      }
    }
    return KeyEventResult.handled;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Focus(
        focusNode: _focus,
        autofocus: true,
        onKeyEvent: _onKey,
        child: GestureDetector(
          onTap: () => _focus.requestFocus(),
          child: Center(
            child: AspectRatio(
              aspectRatio: 16 / 9,
              child: LayoutBuilder(builder: (context, box) {
                final u = box.maxWidth / 480;
                return ClipRect(
                  child: Stack(children: [
                    Positioned.fill(
                      child: RepaintBoundary(
                        child: CustomPaint(painter: GamePainter(game, renderer)),
                      ),
                    ),
                    Positioned.fill(child: Hud(game: game, unit: u)),
                  ]),
                );
              }),
            ),
          ),
        ),
      ),
    );
  }
}

/// 480x270 の低解像度で描いてから最近傍補間で拡大し、ドット感を出す。
class GamePainter extends CustomPainter {
  GamePainter(this.game, this.renderer) : super(repaint: game);

  final Game game;
  final RoadRenderer renderer;

  static const lowW = 480.0, lowH = 270.0;

  @override
  void paint(Canvas canvas, Size size) {
    if (!game.pixelated) {
      canvas.save();
      canvas.clipRect(Offset.zero & size);
      renderer.render(canvas, game, size.width, size.height);
      canvas.restore();
      return;
    }
    final rec = ui.PictureRecorder();
    final c = Canvas(rec, const Rect.fromLTWH(0, 0, lowW, lowH));
    c.clipRect(const Rect.fromLTWH(0, 0, lowW, lowH));
    renderer.render(c, game, lowW, lowH);
    final pic = rec.endRecording();
    final img = pic.toImageSync(lowW.toInt(), lowH.toInt());
    canvas.drawImageRect(
      img,
      const Rect.fromLTWH(0, 0, lowW, lowH),
      Offset.zero & size,
      Paint()..filterQuality = FilterQuality.none,
    );
    img.dispose();
    pic.dispose();
  }

  @override
  bool shouldRepaint(covariant GamePainter old) => true;
}
