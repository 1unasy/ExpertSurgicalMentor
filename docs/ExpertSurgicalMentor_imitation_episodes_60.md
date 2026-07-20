# ExpertSurgicalMentor 모방학습 에피소드 60개

> 목적: OMX-L 교시를 통해 OMX-F가 큰 트레이의 도구를 작은 보조 트레이로 옮기는 동작을 학습하기 위한 에피소드 정의.
> 노란색/주황색 약품은 실제 투약 대상이 아닌 색상 구분용 장난감 약품 모형으로 사용한다.

## 데이터 구성

- 단일 도구 전달 50개: 주사기·주황색 집게·노란색 가위·노란색 약품·주황색 약품 각 10개
- 다중 도구 순차 전달 10개
- Split: train 46개, validation 7개, test 7개

## 공통 Action Sequence

1. MoveToHome
2. MoveAbove(SourceSlot)
3. OpenGripper
4. Descend
5. CloseGripper
6. Lift
7. Transfer(AssistTray)
8. Descend
9. OpenGripper
10. Retreat
11. MoveToHome

## 에피소드 목록

| Episode | Split | Task | Procedure | Target | Variation | Instruction |
|---|---|---|---|---|---|---|
| ESM_EP_001 | train | DELIVER_TOY_SYRINGE | SimulatedWoundIrrigation | ToySyringe | Nominal | Move ToySyringe from MainToolTray.SyringeSlot to AssistTray.Center. |
| ESM_EP_002 | train | DELIVER_TOY_SYRINGE | SimulatedWoundIrrigation | ToySyringe | SourceRight10 | Move ToySyringe from MainToolTray.SyringeSlot to AssistTray.Center. |
| ESM_EP_003 | train | DELIVER_TOY_SYRINGE | SimulatedWoundIrrigation | ToySyringe | SourceLeft10 | Move ToySyringe from MainToolTray.SyringeSlot to AssistTray.Center. |
| ESM_EP_004 | train | DELIVER_TOY_SYRINGE | SimulatedWoundIrrigation | ToySyringe | SourceForward10 | Move ToySyringe from MainToolTray.SyringeSlot to AssistTray.Center. |
| ESM_EP_005 | train | DELIVER_TOY_SYRINGE | SimulatedWoundIrrigation | ToySyringe | SourceBackward10 | Move ToySyringe from MainToolTray.SyringeSlot to AssistTray.Center. |
| ESM_EP_006 | train | DELIVER_TOY_SYRINGE | SimulatedWoundIrrigation | ToySyringe | YawPlus10 | Move ToySyringe from MainToolTray.SyringeSlot to AssistTray.Center. |
| ESM_EP_007 | train | DELIVER_TOY_SYRINGE | SimulatedWoundIrrigation | ToySyringe | YawMinus10 | Move ToySyringe from MainToolTray.SyringeSlot to AssistTray.Center. |
| ESM_EP_008 | train | DELIVER_TOY_SYRINGE | SimulatedWoundIrrigation | ToySyringe | TargetRight10 | Move ToySyringe from MainToolTray.SyringeSlot to AssistTray.Center. |
| ESM_EP_009 | validation | DELIVER_TOY_SYRINGE | SimulatedWoundIrrigation | ToySyringe | TargetBackward10 | Move ToySyringe from MainToolTray.SyringeSlot to AssistTray.Center. |
| ESM_EP_010 | test | DELIVER_TOY_SYRINGE | SimulatedWoundIrrigation | ToySyringe | CombinedSmallVariation | Move ToySyringe from MainToolTray.SyringeSlot to AssistTray.Center. |
| ESM_EP_011 | train | DELIVER_ORANGE_FORCEPS | SimulatedForeignBodyRemoval | OrangeForceps | Nominal | Move OrangeForceps from MainToolTray.ForcepsSlot to AssistTray.Center. |
| ESM_EP_012 | train | DELIVER_ORANGE_FORCEPS | SimulatedForeignBodyRemoval | OrangeForceps | SourceRight10 | Move OrangeForceps from MainToolTray.ForcepsSlot to AssistTray.Center. |
| ESM_EP_013 | train | DELIVER_ORANGE_FORCEPS | SimulatedForeignBodyRemoval | OrangeForceps | SourceLeft10 | Move OrangeForceps from MainToolTray.ForcepsSlot to AssistTray.Center. |
| ESM_EP_014 | train | DELIVER_ORANGE_FORCEPS | SimulatedForeignBodyRemoval | OrangeForceps | SourceForward10 | Move OrangeForceps from MainToolTray.ForcepsSlot to AssistTray.Center. |
| ESM_EP_015 | train | DELIVER_ORANGE_FORCEPS | SimulatedForeignBodyRemoval | OrangeForceps | SourceBackward10 | Move OrangeForceps from MainToolTray.ForcepsSlot to AssistTray.Center. |
| ESM_EP_016 | train | DELIVER_ORANGE_FORCEPS | SimulatedForeignBodyRemoval | OrangeForceps | YawPlus10 | Move OrangeForceps from MainToolTray.ForcepsSlot to AssistTray.Center. |
| ESM_EP_017 | train | DELIVER_ORANGE_FORCEPS | SimulatedForeignBodyRemoval | OrangeForceps | YawMinus10 | Move OrangeForceps from MainToolTray.ForcepsSlot to AssistTray.Center. |
| ESM_EP_018 | train | DELIVER_ORANGE_FORCEPS | SimulatedForeignBodyRemoval | OrangeForceps | TargetRight10 | Move OrangeForceps from MainToolTray.ForcepsSlot to AssistTray.Center. |
| ESM_EP_019 | validation | DELIVER_ORANGE_FORCEPS | SimulatedForeignBodyRemoval | OrangeForceps | TargetBackward10 | Move OrangeForceps from MainToolTray.ForcepsSlot to AssistTray.Center. |
| ESM_EP_020 | test | DELIVER_ORANGE_FORCEPS | SimulatedForeignBodyRemoval | OrangeForceps | CombinedSmallVariation | Move OrangeForceps from MainToolTray.ForcepsSlot to AssistTray.Center. |
| ESM_EP_021 | train | DELIVER_YELLOW_SCISSORS | SimulatedSutureAssistance | YellowScissors | Nominal | Move YellowScissors from MainToolTray.ScissorsSlot to AssistTray.Center. |
| ESM_EP_022 | train | DELIVER_YELLOW_SCISSORS | SimulatedSutureAssistance | YellowScissors | SourceRight10 | Move YellowScissors from MainToolTray.ScissorsSlot to AssistTray.Center. |
| ESM_EP_023 | train | DELIVER_YELLOW_SCISSORS | SimulatedSutureAssistance | YellowScissors | SourceLeft10 | Move YellowScissors from MainToolTray.ScissorsSlot to AssistTray.Center. |
| ESM_EP_024 | train | DELIVER_YELLOW_SCISSORS | SimulatedSutureAssistance | YellowScissors | SourceForward10 | Move YellowScissors from MainToolTray.ScissorsSlot to AssistTray.Center. |
| ESM_EP_025 | train | DELIVER_YELLOW_SCISSORS | SimulatedSutureAssistance | YellowScissors | SourceBackward10 | Move YellowScissors from MainToolTray.ScissorsSlot to AssistTray.Center. |
| ESM_EP_026 | train | DELIVER_YELLOW_SCISSORS | SimulatedSutureAssistance | YellowScissors | YawPlus10 | Move YellowScissors from MainToolTray.ScissorsSlot to AssistTray.Center. |
| ESM_EP_027 | train | DELIVER_YELLOW_SCISSORS | SimulatedSutureAssistance | YellowScissors | YawMinus10 | Move YellowScissors from MainToolTray.ScissorsSlot to AssistTray.Center. |
| ESM_EP_028 | train | DELIVER_YELLOW_SCISSORS | SimulatedSutureAssistance | YellowScissors | TargetRight10 | Move YellowScissors from MainToolTray.ScissorsSlot to AssistTray.Center. |
| ESM_EP_029 | validation | DELIVER_YELLOW_SCISSORS | SimulatedSutureAssistance | YellowScissors | TargetBackward10 | Move YellowScissors from MainToolTray.ScissorsSlot to AssistTray.Center. |
| ESM_EP_030 | test | DELIVER_YELLOW_SCISSORS | SimulatedSutureAssistance | YellowScissors | CombinedSmallVariation | Move YellowScissors from MainToolTray.ScissorsSlot to AssistTray.Center. |
| ESM_EP_031 | train | DELIVER_YELLOW_MEDICATION | ColorCodedMedicationPreparationSimulation | YellowMedication | Nominal | Move YellowMedication from MainToolTray.YellowMedicationSlot to AssistTray.Center. |
| ESM_EP_032 | train | DELIVER_YELLOW_MEDICATION | ColorCodedMedicationPreparationSimulation | YellowMedication | SourceRight10 | Move YellowMedication from MainToolTray.YellowMedicationSlot to AssistTray.Center. |
| ESM_EP_033 | train | DELIVER_YELLOW_MEDICATION | ColorCodedMedicationPreparationSimulation | YellowMedication | SourceLeft10 | Move YellowMedication from MainToolTray.YellowMedicationSlot to AssistTray.Center. |
| ESM_EP_034 | train | DELIVER_YELLOW_MEDICATION | ColorCodedMedicationPreparationSimulation | YellowMedication | SourceForward10 | Move YellowMedication from MainToolTray.YellowMedicationSlot to AssistTray.Center. |
| ESM_EP_035 | train | DELIVER_YELLOW_MEDICATION | ColorCodedMedicationPreparationSimulation | YellowMedication | SourceBackward10 | Move YellowMedication from MainToolTray.YellowMedicationSlot to AssistTray.Center. |
| ESM_EP_036 | train | DELIVER_YELLOW_MEDICATION | ColorCodedMedicationPreparationSimulation | YellowMedication | YawPlus10 | Move YellowMedication from MainToolTray.YellowMedicationSlot to AssistTray.Center. |
| ESM_EP_037 | train | DELIVER_YELLOW_MEDICATION | ColorCodedMedicationPreparationSimulation | YellowMedication | YawMinus10 | Move YellowMedication from MainToolTray.YellowMedicationSlot to AssistTray.Center. |
| ESM_EP_038 | train | DELIVER_YELLOW_MEDICATION | ColorCodedMedicationPreparationSimulation | YellowMedication | TargetRight10 | Move YellowMedication from MainToolTray.YellowMedicationSlot to AssistTray.Center. |
| ESM_EP_039 | validation | DELIVER_YELLOW_MEDICATION | ColorCodedMedicationPreparationSimulation | YellowMedication | TargetBackward10 | Move YellowMedication from MainToolTray.YellowMedicationSlot to AssistTray.Center. |
| ESM_EP_040 | test | DELIVER_YELLOW_MEDICATION | ColorCodedMedicationPreparationSimulation | YellowMedication | CombinedSmallVariation | Move YellowMedication from MainToolTray.YellowMedicationSlot to AssistTray.Center. |
| ESM_EP_041 | train | DELIVER_ORANGE_MEDICATION | ColorCodedMedicationPreparationSimulation | OrangeMedication | Nominal | Move OrangeMedication from MainToolTray.OrangeMedicationSlot to AssistTray.Center. |
| ESM_EP_042 | train | DELIVER_ORANGE_MEDICATION | ColorCodedMedicationPreparationSimulation | OrangeMedication | SourceRight10 | Move OrangeMedication from MainToolTray.OrangeMedicationSlot to AssistTray.Center. |
| ESM_EP_043 | train | DELIVER_ORANGE_MEDICATION | ColorCodedMedicationPreparationSimulation | OrangeMedication | SourceLeft10 | Move OrangeMedication from MainToolTray.OrangeMedicationSlot to AssistTray.Center. |
| ESM_EP_044 | train | DELIVER_ORANGE_MEDICATION | ColorCodedMedicationPreparationSimulation | OrangeMedication | SourceForward10 | Move OrangeMedication from MainToolTray.OrangeMedicationSlot to AssistTray.Center. |
| ESM_EP_045 | train | DELIVER_ORANGE_MEDICATION | ColorCodedMedicationPreparationSimulation | OrangeMedication | SourceBackward10 | Move OrangeMedication from MainToolTray.OrangeMedicationSlot to AssistTray.Center. |
| ESM_EP_046 | train | DELIVER_ORANGE_MEDICATION | ColorCodedMedicationPreparationSimulation | OrangeMedication | YawPlus10 | Move OrangeMedication from MainToolTray.OrangeMedicationSlot to AssistTray.Center. |
| ESM_EP_047 | train | DELIVER_ORANGE_MEDICATION | ColorCodedMedicationPreparationSimulation | OrangeMedication | YawMinus10 | Move OrangeMedication from MainToolTray.OrangeMedicationSlot to AssistTray.Center. |
| ESM_EP_048 | train | DELIVER_ORANGE_MEDICATION | ColorCodedMedicationPreparationSimulation | OrangeMedication | TargetRight10 | Move OrangeMedication from MainToolTray.OrangeMedicationSlot to AssistTray.Center. |
| ESM_EP_049 | validation | DELIVER_ORANGE_MEDICATION | ColorCodedMedicationPreparationSimulation | OrangeMedication | TargetBackward10 | Move OrangeMedication from MainToolTray.OrangeMedicationSlot to AssistTray.Center. |
| ESM_EP_050 | test | DELIVER_ORANGE_MEDICATION | ColorCodedMedicationPreparationSimulation | OrangeMedication | CombinedSmallVariation | Move OrangeMedication from MainToolTray.OrangeMedicationSlot to AssistTray.Center. |
| ESM_EP_051 | train | SEQ_WOUND_01 | SimulatedWoundIrrigation | ToySyringe → OrangeForceps | Nominal | Deliver the listed objects to the assist tray in the specified order: ToySyringe -> OrangeForceps |
| ESM_EP_052 | train | SEQ_WOUND_02 | SimulatedWoundIrrigation | ToySyringe → OrangeForceps | SourceRight10 | Deliver the listed objects to the assist tray in the specified order: ToySyringe -> OrangeForceps |
| ESM_EP_053 | train | SEQ_SUTURE_01 | SimulatedSutureAssistance | OrangeForceps → YellowScissors | SourceLeft10 | Deliver the listed objects to the assist tray in the specified order: OrangeForceps -> YellowScissors |
| ESM_EP_054 | train | SEQ_SUTURE_02 | SimulatedSutureAssistance | OrangeForceps → YellowScissors | SourceForward10 | Deliver the listed objects to the assist tray in the specified order: OrangeForceps -> YellowScissors |
| ESM_EP_055 | train | SEQ_MED_Y_01 | ColorCodedMedicationPreparationSimulation | YellowMedication → ToySyringe | SourceBackward10 | Deliver the listed objects to the assist tray in the specified order: YellowMedication -> ToySyringe |
| ESM_EP_056 | train | SEQ_MED_O_01 | ColorCodedMedicationPreparationSimulation | OrangeMedication → ToySyringe | YawPlus10 | Deliver the listed objects to the assist tray in the specified order: OrangeMedication -> ToySyringe |
| ESM_EP_057 | validation | SEQ_FULL_01 | CombinedTrainingSequence | ToySyringe → OrangeForceps → YellowScissors | YawMinus10 | Deliver the listed objects to the assist tray in the specified order: ToySyringe -> OrangeForceps -> YellowScissors |
| ESM_EP_058 | validation | SEQ_FULL_02 | CombinedTrainingSequence | OrangeForceps → YellowScissors → ToySyringe | TargetRight10 | Deliver the listed objects to the assist tray in the specified order: OrangeForceps -> YellowScissors -> ToySyringe |
| ESM_EP_059 | test | SEQ_COLOR_01 | ColorSelectionTraining | YellowMedication → OrangeMedication | TargetBackward10 | Deliver the listed objects to the assist tray in the specified order: YellowMedication -> OrangeMedication |
| ESM_EP_060 | test | SEQ_COLOR_02 | ColorSelectionTraining | OrangeMedication → YellowMedication | CombinedSmallVariation | Deliver the listed objects to the assist tray in the specified order: OrangeMedication -> YellowMedication |

## 수집 시 주의사항

- 처음에는 모든 도구의 시작 슬롯과 작은 트레이의 목표 슬롯을 고정한다.
- 제안된 ±5~10 mm 및 ±5~10° 변형은 실제 OMX-F 작업 범위와 충돌 여부를 확인한 뒤 적용한다.
- 각 에피소드에는 카메라 영상, joint position, joint velocity, gripper position, task_id, 성공 여부를 저장한다.
- 실패한 시연은 기본 모방학습 학습셋에 넣지 않고 오류 분석 또는 평가셋으로 분리한다.
- 사람 손 위로 직접 도구를 전달하지 않고 작은 트레이 내부에 완전히 놓은 뒤 로봇이 후퇴한다.