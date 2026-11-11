"""Dijkstra 最短路径算法，以及最短路径与各段路程数据的整理"""

import heapq


class SortedPathData:
    """最短路径数据"""

    def __init__(self) -> None:
        """初始化最短路径数据"""
        self.node_id: str = ""
        """ 节点id """
        self.distance: float = 0
        """ 总路程 """
        self.path: list[str] = []
        """ 通往本节点的路径列表 """
        self.path_times: list[int] = []
        """ 通往本节点的路径中各节点路程列表 """


def dijkstra(
    graph: dict[str, dict[str, int]], start: str
) -> dict[str, SortedPathData]:
    """
    使用Dijkstra算法指定节点到其他节点的最短路径
    Keyword arguments:
    graph -- 加权图 {节点id:{可以通往的节点id:路程}}
    start -- 路径起点
    Return arguments:
    Dict[str, SortedPathData] -- 从起点到各个节点的最短路径数据
    """
    distances: dict[str, float] = {
        vertex: float("infinity") for vertex in graph
    }
    previous_nodes: dict[str, str | None] = {vertex: None for vertex in graph}
    distances[start] = 0
    priority_queue = [(0, start)]
    while priority_queue:
        current_distance, current_vertex = heapq.heappop(priority_queue)
        if current_distance > distances[current_vertex]:
            continue
        for neighbor, weight in graph[current_vertex].items():
            distance = current_distance + weight
            if distance < distances[neighbor]:
                distances[neighbor] = distance
                previous_nodes[neighbor] = current_vertex
                heapq.heappush(priority_queue, (distance, neighbor))
    paths_data: dict[str, SortedPathData] = {}
    for vertex in graph:
        path_data = SortedPathData()
        path_data.node_id = vertex
        path_data.distance = distances[vertex]
        path_data.path, path_data.path_times = get_path_and_times(
            previous_nodes, graph, vertex
        )
        paths_data[vertex] = path_data
    return paths_data


def get_path_and_times(
    previous_nodes: dict[str, str | None],
    graph: dict[str, dict[str, int]],
    vertex: str,
) -> tuple[list[str], list[int]]:
    """
    根据前驱节点字典构建到指定节点的路径和时间列表。
    Keyword arguments:
    previous_nodes -- 存储每个节点的前一个节点的字典。
    graph -- 表示加权图的字典。
    vertex -- 目标节点。
    Return arguments:
    Tuple[List[str], List[str]]从起始节点到目标节点的路径和时间列表。
    """
    path: list[str] = []
    path_times = [0]
    current: str | None = vertex
    while current is not None:
        path.append(current)
        previous = previous_nodes[current]
        if previous is not None:
            path_times.append(graph[previous][current])
        current = previous
    return path[::-1], path_times
