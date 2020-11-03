import sys
import os

from SCons.Script import ARGUMENTS, COMMAND_LINE_TARGETS, Import, Return

Import("env")


def get_wdtcfg_fuse():
    return 0x00


def get_bodcfg_fuse(bod):
    if bod == "4.3v":
        return 0xF4
    elif bod == "2.6v":
        return 0x54
    elif bod == "1.8v":
        return 0x14
    else:  # bod disabled
        return 0x00


def get_osccfg_fuse(f_cpu, oscillator):
    if (
        f_cpu == "20000000L" or f_cpu == "10000000L" or f_cpu == "5000000L"
    ) and oscillator == "internal":
        return 0x02
    else:
        return 0x01


def get_tcd0cfg_fuse():
    return 0x00


def get_syscfg0_fuse(eesave, rstpin, uart):
    eesave_bit = 1 if eesave == "yes" else 0
    if rstpin == "gpio":
        if uart == "no_bootloader":
            rstpin_bit = 0
        else:
            rstpin_bit = 1
    else:
        rstpin_bit = 1
    return 0xC0 | rstpin_bit << 3 | eesave_bit


def get_syscfg1_fuse():
    return 0x06


def get_append_fuse():
    return 0x00


def get_bootend_fuse(uart):
    if uart == "no_bootloader":
        return 0x00
    else:
        return 0x02


def get_lockbit_fuse():
    return 0xC5


def print_fuses_info(fuse_values, fuse_names, lock_fuse):
    if "upload" in COMMAND_LINE_TARGETS:
        return
    print("\nSelected fuses:")
    print("------------------------")
    for idx, value in enumerate(fuse_values):
        if value:
            print("[fuse%d / %s = %s]" % (idx, fuse_names[idx].upper(), value))
    if lock_fuse:
        print("[lfuse / LOCKBIT = %s]" % lock_fuse)
    print("------------------------\n")


def calculate_megacorex_fuses(board_config, predefined_fuses):
    megacorex_fuses = []
    f_cpu = board_config.get("build.f_cpu", "16000000L").upper()
    oscillator = board_config.get("hardware.oscillator", "internal").lower()
    bod = board_config.get("hardware.bod", "2.6v").lower()
    uart = board_config.get("hardware.uart", "no_bootloader").lower()
    eesave = board_config.get("hardware.eesave", "yes").lower()
    rstpin = board_config.get("hardware.rstpin", "reset").lower()

    # Guard that prevents the user from turning the reset pin
    # into a GPIO while using a bootloader
    if uart != "no_bootloader":
        rstpin = "reset"

    print("\nTARGET CONFIGURATION:")
    print("------------------------")
    print("Target = %s" % target)
    print("Clock speed = %s" % f_cpu)
    print("Oscillator = %s" % oscillator)
    print("BOD level = %s" % bod)
    print("Save EEPROM = %s" % eesave)
    print("Reset pin mode = %s" % rstpin)
    print("------------------------")

    return (
        predefined_fuses[0] or hex(get_wdtcfg_fuse()),
        predefined_fuses[1] or hex(get_bodcfg_fuse(bod)),
        predefined_fuses[2] or hex(get_osccfg_fuse(f_cpu, oscillator)),
        "",  # reserved
        predefined_fuses[4] or hex(get_tcd0cfg_fuse()),
        predefined_fuses[5] or hex(get_syscfg0_fuse(eesave, rstpin, uart)),
        predefined_fuses[6] or hex(get_syscfg1_fuse()),
        predefined_fuses[7] or hex(get_append_fuse()),
        predefined_fuses[8] or hex(get_bootend_fuse(uart)),
    )


board = env.BoardConfig()
platform = env.PioPlatform()
core = board.get("build.core", "")

target = (
    board.get("build.mcu").lower()
    if board.get("build.mcu", "")
    else env.subst("$BOARD").lower()
)

fuses_section = "fuses"
if "bootloader" in COMMAND_LINE_TARGETS or "UPLOADBOOTCMD" in env:
    fuses_section = "bootloader"

# Note: the index represents the fuse number
fuse_names = (
    "wdtcfg",
    "bodcfg",
    "osccfg",
    "",  # reserved
    "tcd0cfg",
    "syscfg0",
    "syscfg1",
    "append",
    "bootend"
)

board_fuses = board.get(fuses_section, {})
if not board_fuses and "FUSESFLAGS" not in env and core != "MegaCoreX":
    sys.stderr.write(
        "Error: Dynamic fuses generation for %s / %s is not supported. "
        "Please specify fuses in platformio.ini\n" % (core, env.subst("$BOARD"))
    )
    env.Exit(1)

fuse_values = [board_fuses.get(fname, "") for fname in fuse_names]
lock_fuse = board_fuses.get("lockbit", hex(get_lockbit_fuse()))
if core == "MegaCoreX":
    fuse_values = calculate_megacorex_fuses(board, fuse_values)

env.Append(
    FUSESUPLOADER="avrdude",
    FUSESUPLOADERFLAGS=[
        "-p",
        "$BOARD_MCU",
        "-C",
        '"%s"'
        % os.path.join(
            env.PioPlatform().get_package_dir("tool-avrdude-megaavr") or "",
            "avrdude.conf",
        ),
    ],
    SETFUSESCMD="$FUSESUPLOADER $FUSESUPLOADERFLAGS $UPLOAD_FLAGS $FUSESFLAGS",
)

env.Append(
    FUSESFLAGS=[
        "-Ufuse%d:w:%s:m" % (idx, value)
        for idx, value in enumerate(fuse_values)
        if value
    ]
)

if lock_fuse:
    env.Append(FUSESFLAGS=["-Ulock:w:%s:m" % lock_fuse])

if int(ARGUMENTS.get("PIOVERBOSE", 0)):
    env.Append(FUSESUPLOADERFLAGS=["-v"])

if not env.BoardConfig().get("upload", {}).get("require_upload_port", False):
    # upload methods via USB
    env.Append(FUSESUPLOADERFLAGS=["-P", "usb"])
else:
    env.AutodetectUploadPort()
    env.Append(FUSESUPLOADERFLAGS=["-P", '"$UPLOAD_PORT"'])

if env.subst("$UPLOAD_PROTOCOL") != "custom":
    env.Append(FUSESUPLOADERFLAGS=["-c", "$UPLOAD_PROTOCOL"])
else:
    print(
        "Warning: The `custom` upload protocol is used! The upload and fuse flags may "
        "conflict!\nMore information: "
        "https://docs.platformio.org/en/latest/platforms/atmelavr.html"
        "#overriding-default-fuses-command\n"
    )

print_fuses_info(fuse_values, fuse_names, lock_fuse)

fuses_action = env.VerboseAction("$SETFUSESCMD", "Setting fuses...")

Return("fuses_action")
