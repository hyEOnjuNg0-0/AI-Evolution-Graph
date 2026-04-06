from abc import ABC, abstractmethod


class MethodTrendRepositoryPort(ABC):
    """Domain port for fetching method adoption data from the Method Evolution Graph.

    Used by TrendMomentumService to compute CAGR, venue diversity entropy,
    and adoption velocity per method.
    """

    @abstractmethod
    def get_yearly_usage_counts(
        self,
        method_names: list[str],
        year_start: int,
        year_end: int,
    ) -> dict[str, dict[int, int]]:
        """Return yearly paper-usage counts for each method in the requested range.

        A method is "used" in a year when at least one Paper published that year
        has a (:Paper)-[:USES]->(:Method) edge to it.

        Args:
            method_names: Canonical method names to query.
            year_start: First year of the analysis window (inclusive).
            year_end: Last year of the analysis window (inclusive).

        Returns:
            Nested dict: method_name → {year → usage_count}.
            Methods with no usage in the window may be absent from the outer dict.
            Years with zero usage are omitted; callers treat them as count=0.
        """
        raise NotImplementedError

    @abstractmethod
    def get_venue_distribution(
        self,
        method_names: list[str],
        year_start: int,
        year_end: int,
    ) -> dict[str, dict[str, int]]:
        """Return venue-level paper counts for each method in the requested range.

        Only papers with a non-null venue property are included.

        Args:
            method_names: Canonical method names to query.
            year_start: First year of the analysis window (inclusive).
            year_end: Last year of the analysis window (inclusive).

        Returns:
            Nested dict: method_name → {venue_name → paper_count}.
            Methods whose adopting papers all have null venues will be absent.
        """
        raise NotImplementedError

    @abstractmethod
    def get_all_yearly_usage_counts(
        self,
        year_start: int,
        year_end: int,
    ) -> dict[str, dict[int, int]]:
        """Return yearly paper-usage counts for ALL methods in the requested range.

        Same semantics as get_yearly_usage_counts but without a method_names filter,
        used in Discovery mode to rank all known methods.

        Args:
            year_start: First year of the analysis window (inclusive).
            year_end: Last year of the analysis window (inclusive).

        Returns:
            Nested dict: method_name → {year → usage_count}.
        """
        raise NotImplementedError

    @abstractmethod
    def get_all_venue_distributions(
        self,
        year_start: int,
        year_end: int,
    ) -> dict[str, dict[str, int]]:
        """Return venue-level paper counts for ALL methods in the requested range.

        Same semantics as get_venue_distribution but without a method_names filter,
        used in Discovery mode to compute Shannon entropy for all known methods.

        Args:
            year_start: First year of the analysis window (inclusive).
            year_end: Last year of the analysis window (inclusive).

        Returns:
            Nested dict: method_name → {venue_name → paper_count}.
        """
        raise NotImplementedError
