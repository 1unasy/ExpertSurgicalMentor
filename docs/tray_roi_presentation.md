# Main Tray / Assist Tray 좌표 판정

## 발표 핵심 문장

카메라 영상에서 대각선으로 배치된 트레이를 축 정렬 사각형으로 근사하지 않고, 사용자가
선택한 3~8개 꼭짓점의 다각형 ROI로 표현한다. Object YOLO가 검출한 장비 바운딩 박스의
중심점이 어느 다각형 내부에 있는지 계산하여 Main Tray와 Assist Tray를 판정한다.

## 기존 사각형 방식의 문제

`[x1, y1, x2, y2]` 사각형 ROI는 영상 축과 평행하다. 트레이가 대각선이면 실제 트레이 밖의
책상 영역까지 ROI에 포함되어 다음 문제가 발생한다.

- 트레이 밖 물체가 내부 물체로 잘못 판정될 수 있음
- Main/Assist ROI가 겹칠 수 있음
- 트레이 모양과 영상 원근을 정확하게 반영하지 못함

## 다각형 ROI 구성

보정 프로그램은 고정된 front 카메라에서 한 프레임을 가져온다. 사용자는 Main Tray와
Assist Tray의 외곽점을 각각 시계 방향 또는 반시계 방향으로 선택한다.

- 최소 3점, 최대 8점
- 사각형·오각형·육각형 모두 지원
- 선이 서로 교차하지 않도록 외곽 순서대로 선택
- 영상 해상도와 독립적이도록 좌표를 0~1 범위로 정규화

정규화 공식:

```text
x_normalized = x_pixel / image_width
y_normalized = y_pixel / image_height
```

설정 예시:

```json
{
  "camera_index": 4,
  "roi_format": "polygon_v1",
  "main_tray_polygon_normalized": [
    [0.49, 0.08], [0.92, 0.28], [0.75, 1.0], [0.22, 0.84]
  ],
  "assist_tray_polygon_normalized": [
    [0.0, 0.0], [0.49, 0.0], [0.3, 0.64], [0.0, 0.49]
  ]
}
```

## 물체 위치 판정

Object YOLO는 목표 클래스의 바운딩 박스 `[x1, y1, x2, y2]`를 출력한다. 위치 판정에는
박스 중심점을 사용한다.

```text
center_x = (x1 + x2) / 2
center_y = (y1 + y2) / 2
```

OpenCV의 `pointPolygonTest`로 중심점과 각 ROI의 포함 관계를 검사한다.

```text
Main 다각형 내부   → main
Assist 다각형 내부 → assist
두 다각형 외부     → outside
검출 불안정/누락   → unknown
```

## 시간축 안정화

한 프레임의 오검출로 로봇이 움직이지 않도록 총 10프레임을 관찰한다. 같은 트레이에서 목표
물체가 연속 5프레임 확인되어야 위치를 확정한다.

```text
작업 전: main 연속 5프레임   → ACT 실행 허용
작업 후: assist 연속 5프레임 → 성공 및 자동 종료
작업 후: main 연속 5프레임   → 초기 자세에서 제한적 재시도
그 외: unknown               → 추가 동작 차단
```

## 전체 연결 관계

```text
Front Camera
    ↓
Object YOLO (syringe / pill)
    ↓ bounding-box center
Polygon point-in-polygon test
    ├─ Main Tray   → 작업 시작 또는 재시도
    ├─ Assist Tray → 작업 성공
    └─ Unknown     → 안전 중단
```

## 발표 시 강조할 안전 조건

- 카메라 또는 트레이 위치가 바뀌면 ROI를 다시 보정한다.
- Main/Assist 다각형이 서로 겹치지 않도록 설정한다.
- 좌표 판정은 장비의 존재와 위치를 확인할 뿐, 실제 파지 성공 자체를 직접 측정하지는 않는다.
- `unknown`에서는 재시도하지 않는 보수적 정책을 사용한다.

