import os

from rainbow.datadirectory import DataDirectory


class DataSequence:
    """
    Class representing a multi-injection sequence.

    Where a :class:`~rainbow.datadirectory.DataDirectory` is a single
    injection, a DataSequence is the run that produced many of them: an ordered
    set of injections that share one instrument, one method, and (for Agilent)
    a ``sequence.acaml`` document. Each injection is itself a DataDirectory, so
    everything a single read supports still works per injection.

    Args:
        path (str): Path of the sequence directory.
        injections (list): The DataDirectory objects, in acquisition order.
        metadata (dict): Sequence-level metadata. Depends on the vendor.

    Attributes:
        name (str): Name of the sequence directory.
        path (str): Path of the sequence directory.
        injections (list): The DataDirectory objects, in acquisition order.
        by_name (dict): Maps each injection's directory name to its
            DataDirectory.
        metadata (dict): Sequence-level metadata. Depends on the vendor.

    """
    def __init__(self, path, injections, metadata):

        if not isinstance(path, str) or \
           not isinstance(injections, list) or \
           not all(isinstance(inj, DataDirectory) for inj in injections) or \
           not isinstance(metadata, dict):
            raise Exception("Wrong argument parameters for DataSequence.")

        self.path = path
        self.name = os.path.basename(os.path.normpath(path))
        self.injections = injections
        self.metadata = metadata
        self.by_name = {inj.name: inj for inj in injections}

    def __repr__(self):
        return f"{self.name}: {len(self.injections)} injections"

    def __len__(self):
        return len(self.injections)

    def __iter__(self):
        return iter(self.injections)

    def __contains__(self, name):
        """Whether an injection with that directory ``name`` is in the sequence.

        Without this, ``"x.D" in sequence`` fell back to iterating and comparing
        each injection object against a string, so it answered False for a name
        that is present. A membership test that quietly says no is worse than
        one that raises.
        """
        return name in self.by_name

    def __getitem__(self, key):
        """An injection by position, slice, or directory name."""
        if isinstance(key, str):
            return self.get_injection(key)
        if isinstance(key, slice):
            return self.injections[key]
        return self.injections[key]

    def get_injection(self, name):
        """
        Returns an injection by its directory :code:`name`.

        Raises an exception if the :code:`name` is not in the sequence.

        Args:
            name (str): Injection directory name (e.g. ``"008-...01.D"``).

        """
        if name not in self.by_name:
            known = ", ".join(sorted(self.by_name)[:5])
            if len(self.by_name) > 5:
                known += ", ..."
            raise KeyError(
                f"Injection {name!r} not found in {self.name}. "
                f"This sequence has {len(self.by_name)}: {known}")
        return self.by_name[name]

    def get_info(self):
        """
        Returns a string summary of the sequence.

        """
        rule = "=" * len(self.name)
        injections = "\n".join(
            f"  {inj.name}: {' - '.join(d.name for d in inj.datafiles)}"
            for inj in self.injections)
        return f"\n{rule}\n{self.name}\n{rule}\n" \
            f"Sequence Metadata: {self.metadata}\n" \
            f"Injections ({len(self.injections)}):\n{injections}\n"

    def to_asm(self, *, export_dad_cube=True, wavelengths=None, ions=None,
               decimal_places=None, technique=None, utc_offset=None):
        """
        Returns an Allotrope Simple Model (ASM) document for this sequence.

        The document carries one device system document for the run and one
        liquid- or gas-chromatography document per injection. If the sequence
        was read with ``peaks=True``, each injection's integrated peaks become
        its processed data. See :mod:`rainbow.asm` for the scope of the mapping.

        A whole sequence bundles one document per injection, so it can be very
        large. ``export_dad_cube=False``, a ``wavelengths`` subset, and
        ``decimal_places`` each shrink it; for export to disk prefer
        :meth:`export_asm`, which streams.

        Args:
            export_dad_cube (bool, optional): Include multi-wavelength DAD
                spectra as 3D UV spectrum cubes. On by default; the dominant
                size driver, so turning it off shrinks the output sharply.
            wavelengths (float/list, optional): Restrict the DAD spectrum cube
                to these wavelengths (nearest available, in nm); the default
                keeps every wavelength.
            ions (float/list, optional): m/z value(s) to extract from full-scan
                MS data, each exported as its own mass chromatogram. Single-ion
                (SIM) MS is always exported regardless of this argument.
            decimal_places (int, optional): Round emitted numeric
                values to this many decimal places. The default keeps
                full precision.
            technique (str, optional): Force the export technique, ``"GC"`` or
                ``"LC"``, overriding the method's declaration and the
                FID-presence fallback.
            utc_offset (str, optional): UTC offset such as
                ``"-05:00"`` or ``"Z"``, stamped on timestamps the
                instrument recorded without one. An offset the source
                did record is never overridden.

        Returns:
            dict: The ASM document.

        """
        from rainbow import asm
        return asm.sequence_to_asm(self, export_dad_cube=export_dad_cube,
                                   wavelengths=wavelengths, ions=ions,
                                   decimal_places=decimal_places,
                                   technique=technique,
                                   utc_offset=utc_offset)

    def export_asm(self, filename, *, export_dad_cube=True, wavelengths=None,
                   ions=None, decimal_places=None, technique=None,
                   utc_offset=None, indent=2, per_injection=False):
        """
        Writes an Allotrope Simple Model (ASM) JSON document for this sequence.

        The document is streamed to disk one injection at a time, so even a
        long sequence of large spectra never has to fit in memory at once.

        With ``per_injection=True``, ``filename`` is treated as a directory and
        each injection is written as its own standalone document (named for the
        injection), rather than one bundled file. This keeps a long diode-array
        run from producing a single multi-gigabyte file; the method then returns
        the list of paths written.

        Args:
            filename (str): Output JSON file, or the output directory when
                ``per_injection`` is True.
            export_dad_cube (bool, optional): Include multi-wavelength DAD
                spectra as 3D UV spectrum cubes. On by default; turning it off
                shrinks the output sharply.
            wavelengths (float/list, optional): Restrict the DAD spectrum cube
                to these wavelengths (nearest available, in nm); the default
                keeps every wavelength.
            ions (float/list, optional): m/z value(s) to extract from full-scan
                MS data, each exported as its own mass chromatogram. Single-ion
                (SIM) MS is always exported regardless of this argument.
            decimal_places (int, optional): Round emitted numeric
                values to this many decimal places. The default keeps
                full precision.
            technique (str, optional): Force the export technique, ``"GC"`` or
                ``"LC"``, overriding the method's declaration and the
                FID-presence fallback.
            utc_offset (str, optional): UTC offset such as
                ``"-05:00"`` or ``"Z"``, stamped on timestamps the
                instrument recorded without one. An offset the source
                did record is never overridden.
            indent (int, optional): Indentation for the output JSON.
            per_injection (bool, optional): Write one standalone document per
                injection into ``filename`` (a directory) instead of one bundled
                file. Returns the list of paths written.

        """
        from rainbow import asm
        if per_injection:
            return asm.sequence_export_asm_per_injection(
                self, filename, export_dad_cube=export_dad_cube,
                wavelengths=wavelengths, ions=ions,
                decimal_places=decimal_places, technique=technique,
                utc_offset=utc_offset, indent=indent)
        with open(filename, 'w', encoding="utf-8") as f:
            asm.sequence_export_asm(self, f, export_dad_cube=export_dad_cube,
                                    wavelengths=wavelengths, ions=ions,
                                    decimal_places=decimal_places,
                                    technique=technique,
                                    utc_offset=utc_offset, indent=indent)
