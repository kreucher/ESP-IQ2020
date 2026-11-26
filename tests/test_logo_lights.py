#!/usr/bin/env python3
"""Host regression check: python3 -m unittest discover -s tests -v.

Compile the actual logo decoder statements from each component, without an
ESPHome/ESP32 toolchain. CXX (default: c++) must be available. The baseline table
was recorded by compiling the original decoder for every possible input byte.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ("iq2020", "iq2020-dev", "iq2020-legacy")
# Pre-fix outputs, indexed by raw byte. Do not regenerate from the patched code.
BASELINE = bytes.fromhex(
    "0000010000050300000402000000000007070707000000000000000000000000"
    "0606060606060606060606060606060607070707060606060606060606060606"
    "0000000000000000000000000000000007070707000000000000000000000000"
    "0606060606060606060606060606060607070707060606060606060606060606"
    "0000000000000000000000000000000007070707000000000000000000000000"
    "0606060606060606060606060606060607070707060606060606060606060606"
    "0000000000000000000000000000000007070707000000000000000000000000"
    "0606060606060606060606060606060607070707060606060606060606060606"
)


def run_decoder(variant, directory):
    source = (ROOT / "components" / variant / "iq2020.cpp").read_text()
    start = source.index("int logo_lights = 0;")
    end = source.index("if (this->logo_lights_sensor_)", start)
    decoder = source[start:end]
    program = (
        "#include <cstdio>\nint main() { unsigned char processingBuffer[17] = {};\n"
        "for (int value = 0; value < 256; ++value) { processingBuffer[16] = value;\n"
        + decoder + '\nstd::printf("%d ", logo_lights); } }\n'
    )
    cpp = directory / (variant + ".cpp")
    binary = directory / variant
    cpp.write_text(program)
    subprocess.run(
        shlex.split(os.environ.get("CXX", "c++"))
        + ["-std=c++11", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(binary)],
        check=True,
    )
    return bytes(map(int, subprocess.check_output([str(binary)], text=True).split()))


class LogoLightsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        directory = Path(cls.temporary.name)
        cls.actual = {v: run_decoder(v, directory) for v in VARIANTS}

    def test_observed_salt_attention(self):
        # Captured main-status prefix through logo byte16; no private addresses.
        packet = bytes.fromhex("1c1f018680025600080004000006060016")
        self.assertEqual(packet[16], 0x16)
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                self.assertEqual(self.actual[variant][packet[16]], 7)

    def test_only_observed_byte_changes(self):
        self.assertEqual(len(BASELINE), 256)
        self.assertEqual(BASELINE[0x16], 0)
        expected = bytearray(BASELINE)
        expected[0x16] = 7
        for variant in VARIANTS:
            with self.subTest(variant=variant):
                self.assertEqual(self.actual[variant], bytes(expected))

    def test_unknown_values_stay_unknown(self):
        # Nearby 0x14/0x15/0x17 must not become warnings just by relaxing a mask.
        for variant in VARIANTS:
            for value in (0x00, 0x14, 0x15, 0x17, 0x18, 0x1F):
                with self.subTest(variant=variant, raw=hex(value)):
                    self.assertEqual(self.actual[variant][value], 0)


if __name__ == "__main__":
    unittest.main()
