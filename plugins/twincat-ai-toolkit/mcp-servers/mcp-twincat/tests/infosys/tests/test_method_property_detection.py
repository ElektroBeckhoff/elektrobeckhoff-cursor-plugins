"""Unit tests for method, property, and interface type detection."""

from infosys_mshc import detect_type


def test_detect_type_prefixes():
    """Verify prefix detection for standard IEC types."""
    assert detect_type("FB_IotMqttClient") == "FUNCTION_BLOCK"
    assert detect_type("ST_Config") == "STRUCT"
    assert detect_type("E_State") == "ENUM"
    assert detect_type("I_Widget") == "INTERFACE"
    assert detect_type("F_CalcCRC") == "FUNCTION"
    assert detect_type("T_MaxString") == "TYPE"
    assert detect_type("M_Init") == "METHOD"
    assert detect_type("P_Status") == "PROPERTY"


def test_detect_type_keywords():
    """Verify detection of English and German keyword titles."""
    assert detect_type("Method Reset") == "METHOD"
    assert detect_type("Methode Execute") == "METHOD"
    assert detect_type("Property IsConnected") == "PROPERTY"
    assert detect_type("Eigenschaft Status") == "PROPERTY"
    assert detect_type("Function Block TON") == "FUNCTION_BLOCK"
    assert detect_type("Funktionsbaustein PID") == "FUNCTION_BLOCK"
    assert detect_type("Interface I_Base") == "INTERFACE"
    assert detect_type("Schnittstelle I_Device") == "INTERFACE"
    assert detect_type("Overview and Introduction") == "article"
