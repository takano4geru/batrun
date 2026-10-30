import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import 'course.dart';

/// 走行中の一般車。
class TrafficCar {
  TrafficCar(this.s, this.x, this.speed, this.color, this.kind);
  double s;
  final double x;
  final double speed;
  final int color;

  /// 0: 乗用車, 1: トラック, 2: バス
  final int kind;

  double get width => kind == 0 ? 1.8 : 2.4;
  double get height => kind == 0 ? 1.4 : 3.0;
}

enum DayTime { day, evening, night }

class Controls {
  bool left = false;
  bool right = false;
  bool accel = false;
  bool brake = false;
}

/// ゲームの状態と物理。単位は m, s。
class Game extends ChangeNotifier {
  Game(this.course) {
    final rnd = math.Random(7);
    const colors = [
      0xFFE8E8F0, 0xFF2A2F3A, 0xFF3060C0, 0xFFC03030, 0xFFD8D040,
      0xFF808890, 0xFF30A060, 0xFFF0F0F0,
    ];
    for (var i = 0; i < 260; i++) {
      final kind = rnd.nextDouble() < 0.18 ? (rnd.nextBool() ? 1 : 2) : 0;
      traffic.add(TrafficCar(
        200 + rnd.nextDouble() * (course.length - 400),
        rnd.nextBool() ? -lane : lane,
        (kind == 0 ? 17 : 15) + rnd.nextDouble() * 8,
        colors[rnd.nextInt(colors.length)],
        kind,
      ));
    }
  }

  final Course course;

  // 寸法 [m]
  static const double roadHalfWidth = 7.0;
  static const double lane = 2.6;
  static const double cameraHeight = 2.3;
  static const double carAhead = 5.0;
  static const double maxSpeed = 200 / 3.6;

  /// 実データのカーブは疑似3Dでは緩く見えるので強調する倍率。
  double curveScale = 2.5;

  /// カメラ位置 (コース始点からの距離)。自車は carAhead m 先にいる。
  double position = 0;
  double playerX = -lane;
  double speed = 0;
  double steer = 0;
  double bump = 0;
  bool wallHit = false;

  bool started = false;
  bool paused = false;
  bool pixelated = true;
  DayTime timeOfDay = DayTime.day;

  int lap = 1;
  double lapTime = 0;
  double? bestLap;
  double totalTime = 0;
  double _distanceInLap = 0;

  final controls = Controls();
  final traffic = <TrafficCar>[];

  double get playerS => course.wrap(position + carAhead);
  double get speedKmh => speed * 3.6;

  void start() {
    started = true;
    notifyListeners();
  }

  void cycleDayTime() {
    timeOfDay = DayTime.values[(timeOfDay.index + 1) % DayTime.values.length];
    notifyListeners();
  }

  void togglePixelated() {
    pixelated = !pixelated;
    notifyListeners();
  }

  void togglePause() {
    paused = !paused;
    notifyListeners();
  }

  void update(double dt) {
    dt = dt.clamp(0, 1 / 20);
    totalTime += dt;
    for (final c in traffic) {
      c.s = course.wrap(c.s + c.speed * dt);
    }

    if (!started || paused) {
      notifyListeners();
      return;
    }

    final c = controls;
    // 加減速
    if (c.accel) {
      speed += (9.0 * (1 - speed / maxSpeed) + 1.0) * dt;
    } else if (c.brake) {
      speed -= 22 * dt;
    } else {
      speed -= (1.5 + speed * 0.02) * dt;
    }

    // ハンドル。速度が出るほど効きは鈍くなる。
    final target = (c.left ? -1.0 : 0.0) + (c.right ? 1.0 : 0.0);
    steer += (target - steer) * math.min(1, dt * 8);
    final speedRatio = speed / maxSpeed;
    playerX += steer * dt * (4 + 6 * speedRatio) * (speed > 0.5 ? 1 : 0);

    // 遠心力: 実際の曲率 [1/m] × v² に係数をかける。
    final s = playerS;
    final segIdx = (s / course.segmentLength).floor();
    final kappa = course.curve[course.segIndex(segIdx)] / course.segmentLength;
    playerX -= kappa * speed * speed * 0.16 * curveScale / 2.5 * dt;

    // 壁
    const limit = roadHalfWidth - 1.1;
    wallHit = playerX.abs() > limit;
    if (wallHit) {
      playerX = playerX.clamp(-limit, limit);
      speed -= speed * 1.2 * dt;
      bump = 1;
    }

    // 一般車との接触
    for (final t in traffic) {
      var d = t.s - s;
      if (d > course.length / 2) d -= course.length;
      if (d < -course.length / 2) d += course.length;
      if (d > -1.0 && d < 4.2 && (t.x - playerX).abs() < (t.width + 1.8) / 2) {
        speed = math.min(speed, t.speed * 0.7);
        playerX += (playerX >= t.x ? 1 : -1) * 3 * dt;
        bump = 1;
      }
    }

    speed = speed.clamp(0, maxSpeed);
    bump = math.max(0, bump - dt * 3);

    final ds = speed * dt;
    position = course.wrap(position + ds);
    _distanceInLap += ds;
    lapTime += dt;
    if (_distanceInLap >= course.length) {
      _distanceInLap -= course.length;
      bestLap = bestLap == null ? lapTime : math.min(bestLap!, lapTime);
      lapTime = 0;
      lap++;
    }
    notifyListeners();
  }
}
