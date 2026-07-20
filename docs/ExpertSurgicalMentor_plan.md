# ExpertSurgicalMentor 기획안 초안

## 1. 프로젝트 주제

**프로젝트명:** 숙련 수술 멘토 (**ExpertSurgicalMentor**)

**프로젝트 한 줄 정의:**  
가상 수술 케이스를 입력하면 VLM이 필요한 절차와 도구 순서를 생성하고, **OMX-AI 기반 모방학습 로봇팔**이 큰 트레이에 있는 도구를 현재 작업에 맞춰 **앞쪽 작은 보조 트레이**로 옮겨 주며, 카메라가 수련자의 도구 선택과 수행 순서를 추적해 피드백을 제공하는 수술 교육 보조 시스템이다.

> 본 프로젝트는 실제 환자 수술을 지시하거나 의료적 정확성을 보증하는 시스템이 아니다. 장난감 도구와 가상 시나리오를 사용하는 3일 교육용 MVP이다.

---

## 2. 프로젝트 배경

수술 교육은 반복 연습이 중요하지만 실제 환자 데이터 확보, 안전 문제, 숙련자 지도 시간의 제약으로 인해 충분한 반복 훈련 환경을 구성하기 어렵다. 특히 초급 수련자는 다음과 같은 정보를 지속적으로 안내받을 필요가 있다.

- 현재 수행해야 할 단계
- 해당 단계에 필요한 도구
- 도구를 적용해야 하는 연습 구역
- 올바른 단계 순서
- 잘못된 도구 또는 순서를 선택했을 때의 교정 피드백

본 프로젝트는 실제 임상 데이터를 사용하지 않고, **가상 케이스·장난감 의료 도구·표시된 연습 구역**을 활용한다. 실제 의료 전문가의 술기 데이터 대신 팀원이 OMX-L을 조작해 생성한 도구 이송 궤적을 사용하며, OMX-F는 직접 수술하지 않고 **수술 보조자처럼 필요한 도구를 큰 트레이에서 작은 보조 트레이로 옮기는 역할**을 담당한다.

---

## 3. 대목표

가상 수술 케이스 입력부터 도구 전달, 수행 추적, 피드백까지 이어지는 **ROS 2 기반 VLM + 모방학습 통합 MVP**를 구현한다.

1. VLM이 케이스별 Procedure–Phase–Step–Action 절차를 생성한다.
2. 각 Step에 필요한 도구와 대상 위치를 구조화한다.
3. OMX-F가 필요한 도구를 큰 트레이에서 작은 보조 트레이로 옮긴다.
4. 카메라가 수련자의 도구 선택과 작업 구역을 추적한다.
5. 기대 행동과 실제 행동을 비교해 오류 코드와 피드백을 생성한다.

---

## 4. 세부목표

| 구분 | 세부목표 |
|---|---|
| 가상 케이스 | 환자 개인정보 없이 수술 종류, 부위, 난이도, 도구 순서를 JSON으로 정의 |
| 절차 표현 | `Procedure → Phase → Step → Action` 계층과 `Instrument + Verb + Target` 표현 적용 |
| VLM 계획 | 케이스별 단계, 도구, 대상 구역, 다음 행동을 JSON으로 출력 |
| 모방학습 | OMX-L 교시로 큰 트레이 → 작은 트레이 도구 이송 데이터를 수집 |
| 로봇 제어 | OMX-F가 지정 도구를 안전하게 Pick-and-Place하도록 구현 |
| 시각 인식 | 큰 트레이, 작은 트레이, 도구, 약품, 수련자 손 및 연습 구역 검출 |
| 단계 추적 | WrongTool, WrongOrder, WrongTarget, MissedStep, WrongZone 판단 |
| 피드백 | 현재 오류와 다음 행동을 짧은 자연어로 제공 |

---

## 5. 시스템 아키텍처

![시스템 아키텍처](./시스템_아키텍처_다이어그램.png)

### 5.1 계층별 구성

| 계층 | 주요 모듈 | 역할 |
|---|---|---|
| 계획·추론 | VLM Case Planner, Procedure Graph Generator, Feedback Generator | 케이스 해석, 절차 생성, 피드백 생성 |
| 인지·추적 | Camera Calibration, Hand & Tool Detection, Step Tracker, Safety Check | 작업 공간 인식, 도구·손 추적, 단계 및 안전 판정 |
| 제어·모방학습 | Dataset Recorder, Imitation Policy, OMX Follower Controller, OMX Hardware Interface | 교시 데이터 수집, 정책 추론, OMX-F 제어 |

### 5.2 하드웨어 역할

- **User PC:** 케이스 입력, 현재 단계와 결과 확인
- **상단 카메라:** 큰 트레이, 작은 트레이, 도구, 약품, 손, 연습 구역 관찰
- **OMX-L:** 사람이 직접 조작하는 Leader 교시 장치
- **OMX-F:** 필요한 도구를 큰 트레이에서 작은 보조 트레이로 옮기는 Follower
- **큰 트레이:** 사용 가능한 전체 도구와 약품의 초기 위치
- **작은 보조 트레이:** 현재 Step에 필요한 도구를 수련자에게 제공하는 고정 Handoff Zone

---

## 6. VLM + 모방학습 기반 시스템 구현 프로세스

```text
가상 수술 케이스 입력
    ↓
VLM Case Planner
    ↓
Procedure → Phase → Step → Action 생성
    ↓
Step별 필요 도구·대상 구역 결정
    ↓
카메라 캘리브레이션 및 작업 구역 좌표 설정
    ↓
OMX-L Leader 교시 데이터 수집
    ↓
영상 + 관절 상태 + 그리퍼 상태 동기화
    ↓
LeRobot Dataset 또는 ROS 2 Dataset 구성
    ↓
Trajectory Replay / Behavior Cloning / ACT 학습
    ↓
OMX-F: 큰 트레이 → 작은 보조 트레이 도구 전달
    ↓
수련자: 작은 보조 트레이의 도구 사용
    ↓
카메라 기반 도구·손·작업 구역 추적
    ↓
기대 Action과 관찰 Action 비교
    ↓
정상 또는 오류 코드 생성
    ↓
VLM Feedback Generator
    ↓
화면 피드백 및 수행 결과 리포트
```

### 6.1 구현 단계

1. **작업 공간 고정**  
   큰 트레이, 작은 트레이, 연습 구역을 테이프로 고정하고 좌표를 변경하지 않는다.

2. **카메라 캘리브레이션**  
   카메라 내부 파라미터를 확인하고, 상단 영상에서 각 구역의 픽셀 좌표 또는 카메라 3차원 좌표를 정의한다.

3. **도구별 Pick/Place 위치 정의**  
   각 도구의 초기 위치와 작은 보조 트레이의 배치 위치를 OMX-F 기준 waypoint로 저장한다.

4. **Leader 교시 데이터 수집**  
   OMX-L을 조작하여 도구별 `Home → Pick → Lift → Move → Place → Home` 궤적을 반복 수집한다.

5. **모방학습 데이터 구성**  
   카메라 프레임, 관절 위치, 그리퍼 상태, 도구 ID, 작업 ID를 동일 timestamp로 저장한다.

6. **정책 학습 또는 궤적 재생**  
   3일 MVP에서는 trajectory replay를 기본 안정 경로로 확보하고, 시간이 허용되면 Behavior Cloning 또는 ACT를 학습한다.

7. **VLM 계획 연결**  
   VLM이 출력한 `required_instrument`를 ROS 2 작업 명령으로 변환하여 해당 도구 전달 정책을 실행한다.

8. **수련자 단계 평가**  
   수련자가 작은 트레이에서 도구를 가져갔는지, 지정된 연습 구역에 적용했는지, 순서가 맞는지를 규칙 기반 Step Tracker로 판정한다.

---

## 7. 데이터셋: 수술 시나리오 개요

![수술 도구 배치 환경](./수술_도구_배치_환경.jpg)

### 7.1 사용 가능한 도구 및 객체

| ID | 한글명 | 영문명 | 분류 | MVP 역할 |
|---|---|---|---|---|
| T01 | 장난감 주사기 | `ToySyringe` | 도구 | 모의 세척 및 액체 처치 동작 |
| T02 | 주황색 집게 | `OrangeForceps` | 도구 | 대상 고정, 파지, 들어 올리기 |
| T03 | 노란색 가위 | `YellowScissors` | 도구 | 연습용 종이 표시선 또는 모의 실 절단 |
| M01 | 노란색 약품 | `YellowMedication` | 약품 모형 | 색상 기반 약품 선택·전달 훈련 |
| M02 | 주황색 약품 | `OrangeMedication` | 약품 모형 | 색상 기반 약품 선택·전달 훈련 |
| Z01 | 큰 트레이 | `MainToolTray` | 구역 | 모든 도구와 약품의 초기 위치 |
| Z02 | 작은 보조 트레이 | `AssistTray` | 구역 | 현재 Step에 필요한 도구의 전달 위치 |
| Z03 | 연습 구역 | `PracticeZone` | 구역 | 수련자가 모의 처치를 수행하는 위치 |
| Z04 | 반납 구역 | `ReturnZone` | 구역 | 사용 완료 도구를 되돌려 놓는 위치 |

### 7.2 고정 좌표 및 세부 Target

수련자 행동을 정확하게 평가하기 위해 테이블 위에 다음 표식을 부착한다.

| Target ID | 설명 |
|---|---|
| `PracticeZone.Center` | 연습 카드 중앙의 상처 표시 영역 |
| `PracticeZone.Start` | 표시선의 시작점 |
| `PracticeZone.End` | 표시선의 종료점 |
| `PracticeZone.LeftEdge` | 상처 표시의 왼쪽 가장자리 |
| `PracticeZone.RightEdge` | 상처 표시의 오른쪽 가장자리 |
| `PracticeZone.CutPointA` | 연습용 종이 실 또는 표시선을 자르는 지점 |
| `AssistTray.Center` | 로봇이 도구를 내려놓는 기본 위치 |
| `AssistTray.Left/Right` | 두 개 이상의 도구를 순차 배치하는 위치 |
| `MainToolTray.MedYellow` | 노란색 약품 초기 위치 |
| `MainToolTray.MedOrange` | 주황색 약품 초기 위치 |

### 7.3 데이터셋 종류

| 데이터셋 | 입력 | 정답·출력 | 사용 목적 |
|---|---|---|---|
| Case–Plan Dataset | 가상 케이스 JSON | 단계, 필요 도구, Target, 오류 규칙 | VLM 절차 계획 |
| Tool Delivery Dataset | 카메라 영상, 관절 상태, 그리퍼 상태, 작업 ID | 도구별 이송 궤적 | 모방학습 및 OMX-F 제어 |
| Error–Feedback Dataset | 현재 Step, 검출 도구, 손 위치, 작업 구역 | 오류 코드, 다음 Action, 피드백 | 수행 평가 |

---

## 8. 수술 프로세스 계층 정의

```text
Procedure
  └─ Phase
       └─ Step
            └─ Action
```

각 Action은 다음과 같이 정의한다.

```text
Action = Actor + Instrument/Object + Verb + Target
```

예시:

- `Robot + ToySyringe + Pick + MainToolTray`
- `Robot + ToySyringe + Place + AssistTray.Center`
- `Trainee + OrangeForceps + Hold + PracticeZone.LeftEdge`
- `Trainee + YellowScissors + Cut + PracticeZone.CutPointA`
- `Robot + YellowMedication + Place + AssistTray.Center`

---

## 9. 가상 시나리오 10종

아래 시나리오는 실제 수술 술기 지침이 아니라, 현재 보유한 장난감 도구를 이용해 **도구 선택·순서·전달·작업 구역 준수**를 평가하기 위한 교육용 가상 시나리오다.

### 9.1 가상 봉합 수술 보조 케이스

**Case ID:** `SIM_SUTURE_001`  
**목표:** 봉합 전 준비부터 모의 절단 및 종료 정리까지 도구 순서를 학습한다.  
**도구 순서:** 주사기 → 주황색 집게 → 노란색 가위

| Step | 수행 주체 | 도구·객체 | 행동 | 정확한 Target |
|---|---|---|---|---|
| 1 | VLM | Case | 수술 절차와 도구 순서 생성 | Procedure Graph |
| 2 | Robot | ToySyringe | Pick 후 Place | `MainToolTray → AssistTray.Center` |
| 3 | Trainee | ToySyringe | 상처 표시선 세척 동작 | `PracticeZone.Start → PracticeZone.End` |
| 4 | Robot | OrangeForceps | Pick 후 Place | `MainToolTray → AssistTray.Left` |
| 5 | Trainee | OrangeForceps | 상처 가장자리 고정 동작 | `PracticeZone.LeftEdge` 후 `RightEdge` |
| 6 | Robot | YellowScissors | Pick 후 Place | `MainToolTray → AssistTray.Right` |
| 7 | Trainee | YellowScissors | 연습용 종이 표시선 절단 | `PracticeZone.CutPointA` |
| 8 | Trainee | 모든 도구 | 사용 완료 후 반납 | `ReturnZone` |
| 9 | System | Session | 도구 순서와 Target 일치 평가 | 결과 리포트 |

**오류 예:** 가위를 세척 전에 선택, 집게로 `CutPointA` 접근, 도구 미반납

---

### 9.2 가상 봉합사 제거 케이스

**Case ID:** `SIM_SUTURE_REMOVE_001`  
**목표:** 종이 또는 실 모형을 집게로 들어 올린 후 가위로 지정 지점을 절단하는 순서를 학습한다.  
**도구 순서:** 주황색 집게 → 노란색 가위 → 주황색 집게

| Step | 수행 주체 | 도구·객체 | 행동 | 정확한 Target |
|---|---|---|---|---|
| 1 | Robot | OrangeForceps | 전달 | `AssistTray.Left` |
| 2 | Trainee | OrangeForceps | 모의 실의 왼쪽 끝을 들어 올림 | `PracticeZone.LeftEdge` |
| 3 | Robot | YellowScissors | 전달 | `AssistTray.Right` |
| 4 | Trainee | YellowScissors | 지정 절단점 절단 | `PracticeZone.CutPointA` |
| 5 | Trainee | OrangeForceps | 절단된 모형 제거 | `PracticeZone.Center` |
| 6 | Trainee | OrangeForceps | 제거물을 반납 구역에 놓음 | `ReturnZone` |
| 7 | System | Session | Lift → Cut → Remove 순서 평가 | 결과 리포트 |

**오류 예:** 실을 들어 올리기 전에 절단, `CutPointA`가 아닌 위치 절단

---

### 9.3 가상 상처 세척 케이스

**Case ID:** `SIM_IRRIGATION_001`  
**목표:** 주사기 선택과 세척 방향을 평가한다.  
**도구 순서:** 주사기

| Step | 수행 주체 | 도구·객체 | 행동 | 정확한 Target |
|---|---|---|---|---|
| 1 | Robot | ToySyringe | 전달 | `AssistTray.Center` |
| 2 | Trainee | ToySyringe | 파지 | `AssistTray.Center` |
| 3 | Trainee | ToySyringe | 세척 시작 | `PracticeZone.Start` |
| 4 | Trainee | ToySyringe | 일정 방향으로 이동 | `PracticeZone.Start → End` |
| 5 | Trainee | ToySyringe | 종료 및 반납 | `ReturnZone` |
| 6 | System | Session | 올바른 도구와 이동 방향 평가 | 결과 리포트 |

**오류 예:** 집게 선택, End에서 Start 방향으로 수행, 연습 구역 밖에서 수행

---

### 9.4 가상 절개 보조 케이스

**Case ID:** `SIM_INCISION_ASSIST_001`  
**목표:** 집게로 지정 위치를 고정하고 가위로 표시선을 따라 이동하는 도구 교환 순서를 학습한다.  
**도구 순서:** 주황색 집게 → 노란색 가위

| Step | 수행 주체 | 도구·객체 | 행동 | 정확한 Target |
|---|---|---|---|---|
| 1 | Robot | OrangeForceps | 전달 | `AssistTray.Left` |
| 2 | Trainee | OrangeForceps | 왼쪽 가장자리 고정 | `PracticeZone.LeftEdge` |
| 3 | Robot | YellowScissors | 전달 | `AssistTray.Right` |
| 4 | Trainee | YellowScissors | 표시선을 따라 이동 및 모의 절단 | `PracticeZone.Start → End` |
| 5 | Trainee | 도구 | 반납 | `ReturnZone` |
| 6 | System | Session | 집게 고정이 선행되었는지 평가 | 결과 리포트 |

**오류 예:** 집게 고정 없이 가위 사용, 표시선 밖으로 이동

---

### 9.5 가상 조직 고정 보조 케이스

**Case ID:** `SIM_HOLDING_001`  
**목표:** 주황색 집게로 지정된 좌우 위치를 순서대로 고정하는 동작을 평가한다.  
**도구 순서:** 주황색 집게

| Step | 수행 주체 | 도구·객체 | 행동 | 정확한 Target |
|---|---|---|---|---|
| 1 | Robot | OrangeForceps | 전달 | `AssistTray.Center` |
| 2 | Trainee | OrangeForceps | 첫 번째 위치 고정 | `PracticeZone.LeftEdge` |
| 3 | Trainee | OrangeForceps | 두 번째 위치로 이동 | `PracticeZone.RightEdge` |
| 4 | Trainee | OrangeForceps | 중앙 위치 확인 | `PracticeZone.Center` |
| 5 | Trainee | OrangeForceps | 반납 | `ReturnZone` |
| 6 | System | Session | Left → Right → Center 순서 평가 | 결과 리포트 |

**오류 예:** 오른쪽부터 시작, 중앙 구역 누락, 가위 선택

---

### 9.6 가상 수술 중 도구 교환 케이스

**Case ID:** `SIM_TOOL_EXCHANGE_001`  
**목표:** 현재 사용 도구를 반납한 뒤 다음 도구를 받는 교환 절차를 평가한다.  
**도구 순서:** 주사기 → 주황색 집게 → 노란색 가위

| Step | 수행 주체 | 도구·객체 | 행동 | 정확한 Target |
|---|---|---|---|---|
| 1 | Robot | ToySyringe | 전달 | `AssistTray.Center` |
| 2 | Trainee | ToySyringe | 작업 후 반납 | `ReturnZone` |
| 3 | Robot | OrangeForceps | 전달 | `AssistTray.Center` |
| 4 | Trainee | OrangeForceps | 작업 후 반납 | `ReturnZone` |
| 5 | Robot | YellowScissors | 전달 | `AssistTray.Center` |
| 6 | Trainee | YellowScissors | 작업 후 반납 | `ReturnZone` |
| 7 | System | Session | 이전 도구 반납 후 다음 도구가 사용됐는지 평가 | 결과 리포트 |

**오류 예:** 이전 도구가 작은 트레이에 남은 상태에서 다음 도구 사용

---

### 9.7 가상 노란색 약품 준비 케이스

**Case ID:** `SIM_MED_YELLOW_001`  
**목표:** VLM의 약품 색상 지시에 따라 정확한 약품 모형을 선택하고 작은 트레이로 전달한다. 실제 약물명이나 용량은 다루지 않는다.  
**도구·객체 순서:** 노란색 약품

| Step | 수행 주체 | 도구·객체 | 행동 | 정확한 Target |
|---|---|---|---|---|
| 1 | VLM | Medication Order | `YellowMedication` 요청 | Case Plan |
| 2 | Camera | YellowMedication | 위치 확인 | `MainToolTray.MedYellow` |
| 3 | Robot | YellowMedication | Pick | `MainToolTray.MedYellow` |
| 4 | Robot | YellowMedication | Place | `AssistTray.Center` |
| 5 | Trainee | YellowMedication | 색상 확인 | `AssistTray.Center` |
| 6 | System | Session | 요청 색상과 전달 색상 일치 평가 | 결과 리포트 |

**오류 예:** 주황색 약품 전달, 약품을 도구 영역에 배치

---

### 9.8 가상 주황색 약품 준비 케이스

**Case ID:** `SIM_MED_ORANGE_001`  
**목표:** 주황색 약품 모형의 정확한 선택과 전달을 평가한다.  
**도구·객체 순서:** 주황색 약품

| Step | 수행 주체 | 도구·객체 | 행동 | 정확한 Target |
|---|---|---|---|---|
| 1 | VLM | Medication Order | `OrangeMedication` 요청 | Case Plan |
| 2 | Camera | OrangeMedication | 위치 확인 | `MainToolTray.MedOrange` |
| 3 | Robot | OrangeMedication | Pick | `MainToolTray.MedOrange` |
| 4 | Robot | OrangeMedication | Place | `AssistTray.Center` |
| 5 | Trainee | OrangeMedication | 요청 정보와 색상 대조 | `AssistTray.Center` |
| 6 | System | Session | 요청·검출·수령 결과 일치 평가 | 결과 리포트 |

**오류 예:** 노란색 약품 선택, 약품 검출 신뢰도가 낮은데 로봇 실행

---

### 9.9 가상 약품 변경 및 오류 교정 케이스

**Case ID:** `SIM_MED_CHANGE_001`  
**목표:** 잘못 전달된 약품을 회수하고 수정된 약품을 다시 제공하는 오류 복구 절차를 평가한다.  
**도구·객체 순서:** 노란색 약품 회수 → 주황색 약품 전달

| Step | 수행 주체 | 도구·객체 | 행동 | 정확한 Target |
|---|---|---|---|---|
| 1 | Robot | YellowMedication | 최초 전달 | `AssistTray.Center` |
| 2 | System | Case Plan | 요청 불일치 감지 | Expected=`OrangeMedication` |
| 3 | Feedback | Message | 사용 중지 및 회수 안내 | User PC |
| 4 | Robot | YellowMedication | 회수 | `AssistTray.Center → MainToolTray.MedYellow` |
| 5 | Robot | OrangeMedication | 재전달 | `MainToolTray.MedOrange → AssistTray.Center` |
| 6 | Trainee | OrangeMedication | 최종 확인 | `AssistTray.Center` |
| 7 | System | Session | 오류 복구 성공 여부 기록 | 결과 리포트 |

**오류 예:** 잘못된 약품을 회수하지 않고 다음 약품 추가, 변경 지시 무시

---

### 9.10 가상 수술 종료 및 도구 회수 케이스

**Case ID:** `SIM_CLOSEOUT_001`  
**목표:** 사용한 도구와 약품 모형을 정해진 위치로 회수하고 수량 및 위치를 확인한다.  
**회수 대상:** 주사기, 주황색 집게, 노란색 가위, 사용된 약품 모형

| Step | 수행 주체 | 도구·객체 | 행동 | 정확한 Target |
|---|---|---|---|---|
| 1 | System | Session | 종료 단계 진입 | Completion Phase |
| 2 | Trainee | 사용 도구 | 작은 트레이 또는 반납 구역에 정렬 | `ReturnZone` |
| 3 | Camera | ToySyringe | 존재 및 위치 확인 | `ReturnZone` |
| 4 | Camera | OrangeForceps | 존재 및 위치 확인 | `ReturnZone` |
| 5 | Camera | YellowScissors | 존재 및 위치 확인 | `ReturnZone` |
| 6 | Robot | 각 도구 | 원래 위치로 회수 | `MainToolTray`의 지정 슬롯 |
| 7 | System | Medication | 약품 모형 수량 및 색상 확인 | `MedYellow`, `MedOrange` 슬롯 |
| 8 | System | Session | 누락·오배치·미회수 항목 출력 | 결과 리포트 |

**오류 예:** 가위 누락, 집게와 주사기 위치 교환, 약품 모형이 작은 트레이에 남음

---

## 10. 가상 케이스 데이터 예시

```json
{
  "case_id": "SIM_SUTURE_001",
  "case_name": "가상 봉합 수술 보조 케이스",
  "procedure": "SimulatedSutureAssistance",
  "difficulty": "Beginner",
  "available_tools": [
    "ToySyringe",
    "OrangeForceps",
    "YellowScissors",
    "YellowMedication",
    "OrangeMedication"
  ],
  "required_tool_order": [
    "ToySyringe",
    "OrangeForceps",
    "YellowScissors"
  ],
  "robot_role": "Move required items from MainToolTray to AssistTray",
  "expected_actions": [
    {
      "step_id": 1,
      "actor": "Robot",
      "instrument": "ToySyringe",
      "verb": "Place",
      "target": "AssistTray.Center"
    },
    {
      "step_id": 2,
      "actor": "Trainee",
      "instrument": "ToySyringe",
      "verb": "SimulateIrrigation",
      "target": "PracticeZone.StartToEnd"
    }
  ],
  "error_rules": [
    "WrongTool",
    "WrongOrder",
    "WrongTarget",
    "MissedStep",
    "WrongZone"
  ]
}
```

---

## 11. 3인 기능별 To Do List

### 11.1 팀원 1 — VLM·가상 시나리오·피드백 담당

- [ ] 가상 케이스 JSON 스키마 확정
- [ ] 도구·약품·구역 Ontology 확정
- [ ] 10개 가상 시나리오를 Case–Plan Dataset으로 변환
- [ ] Procedure–Phase–Step–Action 생성 프롬프트 작성
- [ ] VLM 출력 JSON Schema 및 validation 구현
- [ ] `required_instrument`, `target`, `next_action` 파싱 구현
- [ ] 오류 코드별 피드백 문장 템플릿 작성
- [ ] 카메라 인식 결과를 VLM 입력 형식으로 변환
- [ ] 세션 종료 리포트 문장 생성
- [ ] VLM이 없는 도구나 실제 약물 용량을 생성하지 못하도록 제약 설정

**주요 산출물**

- `case_dataset.json`
- `procedure_graph.json`
- `vlm_prompt.txt`
- `feedback_rules.json`
- `vlm_case_planner_node.py`

---

### 11.2 팀원 2 — 모방학습·LeRobot·데이터셋 담당

- [ ] OMX-L/OMX-F의 LeRobot 연결 환경 확인
- [ ] 도구별 task ID 정의
- [ ] 카메라 프레임, joint state, gripper state 동기화
- [ ] 도구별 Leader 교시 궤적 5~10회 수집
- [ ] LeRobot Dataset 형식으로 episode 저장
- [ ] 데이터 시각화 및 실패 episode 제거
- [ ] Train/Validation split 구성
- [ ] trajectory replay 기준선 구현
- [ ] Behavior Cloning 또는 ACT 정책 학습
- [ ] 도구별 Pick-and-Place 성공률 평가
- [ ] 정책 실패 시 replay로 전환하는 fallback 정의

**주요 산출물**

- `lerobot_dataset/`
- `trajectory_replay.py`
- `train_act.sh`
- `imitation_policy/`
- `evaluation_results.csv`

---

### 11.3 팀원 3 — 로봇제어·ROS 2·카메라 인식·통합 담당

- [ ] OMX-L/OMX-F 포트와 DYNAMIXEL 통신 확인
- [ ] ROS 2 joint state 및 trajectory command 확인
- [ ] 상단 카메라 설치와 내부 파라미터 확인
- [ ] MainToolTray, AssistTray, PracticeZone, ReturnZone 좌표 정의
- [ ] 도구별 고정 Pick waypoint 설정
- [ ] AssistTray 배치 waypoint 설정
- [ ] 로봇 Home pose와 안전 높이 설정
- [ ] 도구·약품 검출 모델 또는 마커 기반 인식 구현
- [ ] 수련자 손과 Zone 진입 여부 추적
- [ ] Step Tracker와 Safety Check 노드 구현
- [ ] VLM 명령 → 로봇 task 변환 ROS 2 인터페이스 구현
- [ ] 충돌·작업 범위·비상 정지 테스트

**주요 산출물**

- `omx_hardware_node.py`
- `tool_detection_node.py`
- `step_tracker_node.py`
- `workspace_config.yaml`
- `robot_waypoints.yaml`
- `launch/expert_surgical_mentor.launch.py`

---

### 11.4 세 명 공통 통합 작업

- [ ] 정상 케이스 1개 end-to-end 실행
- [ ] WrongTool 케이스 실행
- [ ] WrongOrder 또는 WrongMedication 케이스 실행
- [ ] 입력부터 리포트까지 로그 저장
- [ ] 데모 실패 시 수동 replay 경로 준비
- [ ] 발표용 시연 영상 촬영

---

## 12. 3일 MVP 우선순위

### Day 1 — 환경 및 기준 동작

- 팀원 1: Case JSON, 시나리오 3개 우선 정의
- 팀원 2: LeRobot 또는 ROS 2 기반 데이터 수집 확인
- 팀원 3: 카메라·로봇 연결, waypoint, zone 설정

### Day 2 — 기능 구현

- 팀원 1: VLM 계획 및 피드백 JSON 출력
- 팀원 2: 도구별 episode 수집, replay 및 ACT 학습 시도
- 팀원 3: 도구 검출, 로봇 전달, Step Tracker 연결

### Day 3 — 통합 및 시연

- 필수 시나리오: 도구 교환 또는 가상 봉합 보조
- 약품 시나리오: 노란색/주황색 약품 선택 오류 데모
- 최종 리포트, 영상 및 발표 자료 완성

---

## 13. MVP 성공 기준

| 항목 | 최소 성공 기준 |
|---|---|
| VLM 계획 | Case 1개 이상에서 올바른 도구 순서 JSON 출력 |
| 로봇 전달 | 3개 도구 중 2개 이상을 큰 트레이에서 작은 트레이로 이동 |
| 모방학습 | 1개 도구에 대해 학습 정책 또는 trajectory replay 성공 |
| 시각 인식 | 주사기, 주황색 집게, 노란색 가위, 두 약품 구분 |
| 단계 추적 | 정상 순서와 WrongTool 또는 WrongMedication 구분 |
| 피드백 | 오류 코드에 맞는 다음 행동 안내 출력 |
| 안전 | 사람 손에 직접 전달하지 않고 작은 보조 트레이에만 배치 |

---

## 14. 최종 정의

**ExpertSurgicalMentor**는 실제 수술을 수행하거나 의료 판단을 대신하는 시스템이 아니다. 가상 수술 케이스를 기반으로 도구 사용 순서를 계획하고, OMX-F가 수술 보조자처럼 큰 트레이의 도구와 약품 모형을 작은 보조 트레이로 전달하며, 수련자의 도구 선택과 작업 순서를 추적해 피드백하는 **VLM + 모방학습 기반 Physical AI 교육 프로토타입**이다.
