from abc import ABC, abstractmethod


class CitationTimeSeriesRepositoryPort(ABC):
    """Domain port for fetching yearly citation counts for a set of papers.

    Used by BreakthroughDetectionService to run Kleinberg burst detection
    and to compute centrality shift between time windows.
    """

    @abstractmethod
    def get_yearly_citation_counts(
        self,
        paper_ids: list[str],
        year_start: int,
        year_end: int,
    ) -> dict[str, dict[int, int]]:
        """Return yearly citation counts for each paper in the requested range.

        Only years with at least one incoming citation are guaranteed to appear;
        callers must treat missing years as count=0.

        Args:
            paper_ids: IDs of papers whose incoming citations to aggregate.
            year_start: First year of the analysis window (inclusive).
            year_end: Last year of the analysis window (inclusive).

        Returns:
            Nested dict: paper_id → {year → citation_count}.
            Papers with no citations in the window may be absent from the outer dict.
        """
        raise NotImplementedError
