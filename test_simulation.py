import time
import sys
from haptic_manager import HapticManager

def test_haptic_patterns():
    print("=== bHaptics 촉각슈트 진동 패턴 시뮬레이션 테스트 ===")
    mgr = HapticManager()
    mgr.start()
    
    time.sleep(1.0)
    if not mgr.is_connected():
        print("[주의] bHaptics Player가 실행되어 있지 않거나 연결되지 않았습니다.")
        print("       (bHaptics Player를 켠 후 다시 시도해 주세요)")
    else:
        print("[성공] bHaptics Player와 WebSocket 정상 연결됨!")
    
    print("\n1. 약공격 (Light Hit - 20% 데미지) 테스트...")
    mgr.trigger_damage("light")
    time.sleep(1.5)

    print("2. 중공격 (Medium Hit - 50% 데미지) 테스트...")
    mgr.trigger_damage("medium")
    time.sleep(1.5)

    print("3. 강공격 (Heavy Hit - 80% 데미지) 테스트...")
    mgr.trigger_damage("heavy")
    time.sleep(2.0)

    print("4. 치명타 (Critical KO) 테스트...")
    mgr.trigger_damage("critical")
    time.sleep(2.5)

    print("\n모든 햅틱 테스트 완료.")
    mgr.stop()

if __name__ == "__main__":
    test_haptic_patterns()
