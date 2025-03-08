"""
Hardware control for AlliedVision cameras via the Vimba-X :mod:`vmbpy` interface.
This class also supports backwards compatibility with the
`archived <https://github.com/alliedvision/VimbaPython>`_ :mod:`vimba` interface.
Install :mod:`vmbpy` by following the
`provided instructions <https://github.com/alliedvision/VmbPy>`_.
Be sure to include the ``numpy`` flag in the ``pip install`` command,
as the :class:`AlliedVision` class makes use of these features. See especially the
`vimba python manual <https://github.com/alliedvision/VimbaPython/blob/master/Documentation/Vimba%20Python%20Manual.pdf>`_
for reference.

Note
~~~~
Color camera functionality is not currently implemented, and will lead to undefined behavior.
"""

import time
import numpy as np
import warnings
from typing import Any

from slmsuite.hardware.cameras.camera import Camera

try:
    import vmbpy

    vimba_system = vmbpy.VmbSystem
    vimba_name = "vmbpy"
except ImportError:
    try:
        import vimba

        vimba_system = vimba.Vimba
        vimba_name = "vimba"
        warnings.warn("vmbpy not installed; falling back to vimba")
    except ImportError:
        vimba_system = None
        vimba_name = ""
        warnings.warn(
            "vimba or vmbpy are not installed. Install to use AlliedVision cameras."
        )


class AlliedVision(Camera):
    sdk: vmbpy.VmbSystem | vimba.Vimba | None = None
    cam: vmbpy.Camera | vimba.Camera

    def __init__(
        self,
        serial: str = "",
        pitch_um: tuple[float, float] | None = None,
        verbose: bool = True,
        **kwargs: Any,
    ) -> None:
        if vimba_system is None:
            raise ImportError(
                "vimba or vmbpy are not installed. Install to use AlliedVision cameras."
            )

        if AlliedVision.sdk is None:
            if verbose:
                print(f"{vimba_name} initializing... ", end="")
            AlliedVision.sdk = vimba_system.get_instance()
            AlliedVision.sdk.__enter__()
            if verbose:
                print("success")

        if verbose:
            print("Looking for cameras... ", end="")
        camera_list = AlliedVision.sdk.get_all_cameras()
        if verbose:
            print("success")

        serial_list = [cam.get_serial() for cam in camera_list]
        if serial == "":
            if len(camera_list) == 0:
                raise RuntimeError(f"No cameras found by {vimba_name}.")
            if len(camera_list) > 1 and verbose:
                print(f"No serial given... Choosing first of {serial_list}")

            self.cam = camera_list[0]
            serial = self.cam.get_serial()
        else:
            if serial in serial_list:
                self.cam = camera_list[serial_list.index(serial)]
            else:
                raise RuntimeError(
                    f"Serial {serial} not found by {vimba_name}. Available: {serial_list}"
                )

        if verbose:
            print(f"{vimba_name} sn '{serial}' initializing... ", end="")
        self.cam.__enter__()
        if verbose:
            print("success")

        try:
            self.cam.BinningHorizontal.set(1)
            self.cam.BinningVertical.set(1)
        except:
            pass  # Some cameras do not have the option to set binning.

        self.cam.GainAuto.set("Off")
        self.cam.ExposureAuto.set("Off")
        self.cam.ExposureMode.set("Timed")
        self.cam.AcquisitionMode.set("SingleFrame")
        self.cam.TriggerSelector.set("AcquisitionStart")
        self.cam.TriggerMode.set("Off")
        self.cam.TriggerActivation.set("RisingEdge")
        self.cam.TriggerSource.set("Software")

        super().__init__(
            (self.cam.SensorWidth.get(), self.cam.SensorHeight.get()),
            bitdepth=int(self.cam.PixelSize.get()),
            pitch_um=pitch_um,
            name=serial,
            **kwargs,
        )

    def close(self, close_sdk: bool = True) -> None:
        self.cam.__exit__(None, None, None)
        if close_sdk:
            self.close_sdk()
        del self.cam

    @staticmethod
    def info(verbose: bool = True) -> list[str]:
        if vimba_system is None:
            raise ImportError(
                "vimba or vmbpy are not installed. Install to use AlliedVision cameras."
            )

        if AlliedVision.sdk is None:
            AlliedVision.sdk = vimba_system.get_instance()
            AlliedVision.sdk.__enter__()
            close_sdk = True
        else:
            close_sdk = False

        camera_list = AlliedVision.sdk.get_all_cameras()
        serial_list = [cam.get_serial() for cam in camera_list]

        if verbose:
            print(f"{vimba_name} serials:")
            for serial in serial_list:
                print(f"'{serial}'")

        if close_sdk:
            AlliedVision.close_sdk()

        return serial_list

    @classmethod
    def close_sdk(cls) -> None:
        if cls.sdk is not None:
            cls.sdk.__exit__(None, None, None)
            cls.sdk = None

    def get_properties(self, properties: dict | None = None) -> None:
        if properties is None:
            properties = self.cam.__dict__.keys()

        for key in properties:
            prop = self.cam.__dict__[key]
            try:
                print(prop.get_name(), end="\t")
            except BaseException as e:
                print(f"Error accessing property dictionary, '{key}':{e}")
                continue

            try:
                print(prop.get(), end="\t")
            except:
                pass

            try:
                print(prop.get_unit(), end="\t")
            except:
                pass

            try:
                print(prop.get_description(), end="\n")
            except:
                print("")

    def set_adc_bitdepth(self, bitdepth: int) -> None:
        bitdepth = int(bitdepth)
        for entry in self.cam.SensorBitDepth.get_all_entries():
            value = entry.as_tuple()  # (name : str, value : int)
            if str(bitdepth) in value[0]:
                self.cam.SensorBitDepth.set(value[1])
                break
            raise RuntimeError(f"ADC bitdepth {bitdepth} not found.")

    def get_adc_bitdepth(self) -> int:
        value = str(self.cam.SensorBitDepth.get())
        bitdepth = int("".join(char for char in value if char.isdigit()))
        return bitdepth

    def _get_exposure_hw(self) -> float:
        return float(self.cam.ExposureTime.get()) / 1e6

    def _set_exposure_hw(self, exposure_s: float) -> None:
        self.cam.ExposureTime.set(float(exposure_s * 1e6))

    def set_woi(self, woi: Any = None) -> None:
        return

    def _get_image_hw(self, timeout_s: float) -> np.ndarray:
        t = time.time()
        frame = self.cam.get_frame(timeout_ms=int(1e3 * timeout_s))
        frame = frame.as_numpy_ndarray()
        while np.sum(frame) == np.amax(frame) == 31 and time.time() - t < timeout_s:
            frame = self.cam.get_frame(timeout_ms=int(1e3 * timeout_s))
            frame = frame.as_numpy_ndarray()
        return np.squeeze(frame)
