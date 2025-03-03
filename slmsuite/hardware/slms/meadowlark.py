"""
Hardware control for Meadowlark SLMs.
Tested with:
    Meadowlark (AVR Optics) P1920-400-800-HDMI-T.
    Meadowlark  (AVR Optics) HSPDM512–1064-PCIe8-ODP
    Meadowlark  (AVR Optics) HSP1920-1064-HSP8
Note
~~~~
Check that the Blink SDK, including DLL files etc, are in the default folder
or otherwise pass the correct directory in the constructor.
"""

import os
import ctypes
import warnings
from pathlib import Path
from slmsuite.hardware.slms.slm import SLM

#: str: Default location in which Meadowlark Optics software is installed
_DEFAULT_MEADOWLARK_PATH = "C:\\Program Files\\Meadowlark Optics\\"


def _get_meadowlark_sdk_path(search_path: str = _DEFAULT_MEADOWLARK_PATH) -> str:
    """
    Infers the location of the Meadowlark SDK.

    Parameters
    ----------
    search_path : str
        Path to search for the Meadowlark SDK.

    Returns
    -------
    str
        The path to the Meadowlark SDK folder.

    Raises
    ------
    FileNotFoundError
        If no Blink_C_Wrapper.dll files are found in provided path.

    """
    # Locate the Meadowlark SDK. If there are multiple, default to the
    # most recent one. The search specifies the dynamic link library file because
    # the search will always return multiple files otherwise (.e.g., header), and
    # give false alarm warnings.
    files = {file for file in Path(search_path).rglob("*Blink_C_Wrapper*dll")}
    if len(files) == 1:
        return str(files.pop().parent)
    elif len(files) >= 1:
        sdk_path_ = max(files, key=os.path.getctime).parent
        warnings.warn(
            f"Multiple Meadowlark SDKs located. Defaulting to the most recent one"
            f" {sdk_path_}."
        )
        return str(sdk_path_)
    else:
        raise FileNotFoundError(f"No Blink_C_Wrapper.dll files found in '{sdk_path}'.")


class Meadowlark(SLM):
    """
    Interfaces with Meadowlark SLMs.

    Attributes
    ----------
    slm_lib : ctypes.CDLL
        Connection to the Meadowlark library.
    sdk_path : str
        Path of the Blink SDK folder.
    """

    def __init__(
        self,
        verbose: bool = True,
        sdk_path: str | None = None,
        lut_path: str | None = None,
        wav_um: float = 1,
        pitch_um: tuple[float, float] = (8, 8),
        **kwargs,
    ):
        r"""
        Initializes an instance of a Meadowlark SLM.

        Caution
        ~~~~~~~
        :class:`.Meadowlark` defaults to 8 micron SLM pixel size.
        This is valid for most Meadowlark models, but not true for all!

        Arguments
        ---------
        verbose : bool
            Whether to print extra information.
        sdk_path : str
            Path of the Blink SDK installation folder. Stored in :attr:`sdk_path`.

            Important
            ~~~~~~~~~
            If the installation is not in the default folder,
            then this path needs to be specified
        lut_path : str OR None
            Passed to :meth:`load_lut`. Looks for the voltage 'look-up table' data
            which is necessary to run the SLM.

            Tip
            ~~~
            See :meth:`load_lut` for how the default
            argument and other options are parsed.
        wav_um : float
            Wavelength of operation in microns. Defaults to 1 um.
        pitch_um : (float, float)
            Pixel pitch in microns. Defaults to 8 micron square pixels.
        **kwargs
            See :meth:`.SLM.__init__` for permissible options.
        """

        self.sdk_path = sdk_path if sdk_path else _get_meadowlark_sdk_path()

        # Validates the DPI awareness of this context, which is presumably important for scaling.
        if verbose:
            print("Validating DPI awareness...", end="")

        awareness = ctypes.c_int()
        error_get = ctypes.windll.shcore.GetProcessDpiAwareness(
            0, ctypes.byref(awareness)
        )
        error_set = ctypes.windll.shcore.SetProcessDpiAwareness(2)
        success = ctypes.windll.user32.SetProcessDPIAware()
        # TODO: Implement this call only for HDMI SLMs?

        if not success:
            raise RuntimeError(
                "Meadowlark failed to validate DPI awareness. "
                "Errors: get={}, set={}, awareness={}".format(
                    error_get, error_set, awareness.value
                )
            )
        if verbose:
            print("success")

        # Open the SLM library
        if verbose:
            print("Constructing Blink SDK...", end="")

        # TODO: Add more logic here1
        dll_path = os.path.join(sdk_path, "SDK", "Blink_C_wrapper")
        try:
            ctypes.cdll.LoadLibrary(dll_path)
            self.slm_lib = ctypes.CDLL("Blink_C_wrapper")
        except:
            print("failure")
            raise ImportError(
                f"Meadowlark .dlls did not did not import correctly. "
                f"Is '{dll_path}' the correct path?"
            )

        self.sdk_path = sdk_path

        # Initialize the SDK. The requirements of Matlab, LabVIEW, C++ and Python are different, so pass
        # the constructor a boolean indicating if we are calling from C++/Python (true), or Matlab/LabVIEW (false)
        bool_cpp_or_python = ctypes.c_uint(1)
        self.slm_lib.Create_SDK(bool_cpp_or_python)

        # Adjust pre- and post-ramp slopes for accurate voltage setting
        # (otherwise, custom LUT calibration is not properly implemented [this feature is not implemented in slmsuite]).
        # You may need a special version of the SDK sent to you from Meadowlark to have access to these parameters.
        # self.slm_lib.SetPreRampSlope(20) # default is 7
        # self.slm_lib.SetPostRampSlope(24) # default is 24

        if verbose:
            print("success")

        # Load LUT.
        if verbose:
            print("Loading LUT file...", end="")

        try:
            true_lut_path = self.load_lut(lut_path)
        except RuntimeError as e:
            if verbose:
                print("failure\n(could not find .lut file)")
            raise e
        else:
            if verbose and true_lut_path != lut_path:
                print(f"success\n(loaded from '{true_lut_path}')")

        # Construct other variables.
        super().__init__(
            (self.slm_lib.Get_Width(), self.slm_lib.Get_Height()),
            bitdepth=self.slm_lib.Get_Depth(),
            name=kwargs.pop("name", "Meadowlark"),
            wav_um=wav_um,
            pitch_um=pitch_um,
            **kwargs,
        )

        if self.bitdepth > 8:
            warnings.warn(
                f"Bitdepth of {self.bitdepth} > 8 detected; "
                "this has not been tested and might fail."
            )

        self.set_phase(None)

    def load_lut(self, lut_path=None):
        """
        Loads a voltage 'look-up table' (LUT) to the SLM.
        This converts requested phase values to physical voltage perturbing
        the liquid crystals.

        Parameters
        ----------
        lut_path : str OR None
            Path to look for an LUT file in.

            -   If this is a .lut file, then this file is loaded to the SLM.
            -   If this is a directory, then searches all files inside the
                directory, and loads either the alphabetically-first .lut file
                or if possible the alphabetically-first .lut file starting with ``"slm"``
                which is more likely to correspond to the LUT customized to an SLM,
                as Meadowlark sends such files prefixed by
                ``"slm"`` such as ``"slm5758_at532.lut"``.

        Raises
        ------
        RuntimeError
            If a .lut file is not found.

        Returns
        -------
        str
            The path which was used to load the LUT.
        """
        # If a path is not given, search inside the SDK path.
        if lut_path is None:
            lut_path = os.path.join(self.sdk_path, "LUT Files")

        # If we already have a .lut file, proceed.
        if len(lut_path) > 4 and lut_path[-4:] == ".lut":
            pass
        else:  # Otherwise, treat the path like a folder and search inside the folder.
            lut_file = None

            for file in os.listdir(lut_path):
                # Only examine .lut files.
                if len(file) >= 4 and file[-4:].lower() == ".lut":
                    # Choose the first one.
                    if lut_file is None:
                        lut_file = file

                    # Or choose the first one that starts with "slm"
                    if file[:3].lower() == "slm" and not lut_file[:3].lower() == "slm":
                        lut_file = file
                        break

            # Throw an error if we didn't find a .lut file.
            if lut_file is not None:
                lut_path = os.path.join(lut_path, lut_file)
            else:
                raise RuntimeError(f"Could not find a .lut file at path '{lut_path}'")

        # Finally, load the lookup table.
        self.slm_lib.Load_lut(lut_path)

        return lut_path

    # TODO: Implement this call

    @staticmethod
    def info(verbose=True):
        """
        The normal behavior of this function is to discover the names of all the displays
        to help the user identify the correct display. However, Meadowlark software does
        not currently support multiple SLMs, so this function instead raises an error.

        Parameters
        ----------
        verbose : bool
            Whether to print the discovered information.

        Raises
        ------
        NotImplementedError
        """
        raise NotImplementedError(
            "Meadowlark software does not currently support multiple SLMs, "
            "so a function to identify SLMs is moot. "
            "If functionality with multiple SLMs is desired, contact them directly."
        )

    # TODO: Implement this call

    def close(self):
        """
        See :meth:`.SLM.close`.
        """
        self.slm_lib.Delete_SDK()

    def _set_phase_hw(self, display):
        """
        See :meth:`.SLM._set_phase_hw`.
        """
        self.slm_lib.Write_image(
            display.ctypes.data_as(ctypes.POINTER(ctypes.c_ubyte)),
            ctypes.c_uint(self.bitdepth == 8),  # Is 8-bit
        )

    # TODO: Implement this call

    ### Additional Meadowlark-specific functionality

    def get_temperature(self):
        """
        Read the temperature of the SLM.

        Returns
        -------
        float
            Temperature in degrees celcius.
        """
        return self.slm_lib.Get_SLMTemp()

    # TODO: Implement this call

    def get_coverglass_voltage(self):
        """
        Read the voltage of the SLM coverglass.

        Returns
        -------
        float
            Voltage of the SLM coverglass.
        """
        return self.slm_lib.Get_SLMVCom()

    # TODO: Implement this call
