"""Medical subsystem package - 医疗系统子模块"""

# 显式导入医疗系统的后端子模块，供包级导入并便于 PyInstaller 打包
# 两个界面面板模块（medical_department_panel、medical_player_diagnose_panel）由调用方按名导入
# 按依赖顺序先导入基础模块再导入上层模块，避免循环导入

# 第一层：基础常量和工具模块（无内部依赖）
from Script.System.Medical_System import medical_constant
from Script.System.Medical_System import medical_core
from Script.System.Medical_System import log_system

# 第二层：病人管理模块（依赖基础模块）
from Script.System.Medical_System import clinic_patient_management
from Script.System.Medical_System import hospital_patient_management

# 第三层：医生服务模块（依赖病人管理模块）
from Script.System.Medical_System import clinic_doctor_service
from Script.System.Medical_System import hospital_doctor_service

# 第四层：高层服务与玩家诊疗逻辑模块（前者依赖前三层模块，后者依赖基础模块与 medical_service）
from Script.System.Medical_System import medical_service
from Script.System.Medical_System import medical_player_diagnose_function

__all__ = [
    "medical_constant",
    "medical_core",
    "log_system",
    "clinic_patient_management",
    "hospital_patient_management",
    "clinic_doctor_service",
    "hospital_doctor_service",
    "medical_service",
    "medical_player_diagnose_function",
]
