import numpy as np

from rubber_tracker.utils import ProcessLogger, load_config

class Tracker(ProcessLogger):
    
    def __init__(self):
        super().__init__(self.__class__.__name__)
        config = load_config()
        
        self.iou_threshold = config["tracker"]["iou_threshold"]
        self.old_threshold = config["tracker"]["old_threshold"]
        
        self.tracks = []
        self.new_track_id = 0
        
    def update(self, boxes):
        N = len(boxes)
        boxes_track_id = np.full(N, -1, dtype=int)
        boxes_is_new_track = np.zeros(N, dtype=bool)
        boxes_ages = np.zeros(N, dtype=int)
        
        iou_list = []
        for track_index, track in enumerate(self.tracks):
            
            # Step 1: 모든 track의 'active'를 False로 초기화
            track['active'] = False
            track['old'] += 1
            
            # Step 2: 모든 track과 box의 IoU를 계산하여 리스트에 저장
            track_x1, track_y1, track_x2, track_y2 = track['bbox']
            
            for box_index, (x1, y1, x2, y2) in enumerate(boxes):
                iou = self._compute_iou((x1, y1, x2, y2), (track_x1, track_y1, track_x2, track_y2))
                iou_list.append((track_index, box_index, iou))
        
        # IoU 기준으로 내림차순 정렬
        iou_list.sort(key=lambda x: x[2], reverse=True)
        
        matched_tracks = set()
        matched_boxes = set()
        
        # Step 3: 높은 IoU부터 순차적으로 track과 box 매칭
        for track_index, box_index, iou in iou_list:
            if iou < self.iou_threshold:
                continue
            
            # 이미 매칭된 track이나 box는 건너뜀
            if track_index in matched_tracks or box_index in matched_boxes:
                continue
            
            # 매칭이 가능한 경우, track 업데이트
            x1, y1, x2, y2 = boxes[box_index]
            
            self.tracks[track_index]['bbox'] = (x1, y1, x2, y2)
            self.tracks[track_index]['active'] = True
            self.tracks[track_index]['old'] = 0
            self.tracks[track_index]['age'] += 1
                                
            matched_tracks.add(track_index)
            matched_boxes.add(box_index)
            boxes_track_id[box_index] = self.tracks[track_index]['id']
            boxes_ages[box_index] = self.tracks[track_index]['age']
            
        # Step 4: 매칭되지 않은 boxes에 대해 새로운 track 생성
        for box_index, (x1, y1, x2, y2) in enumerate(boxes):
            if box_index in matched_boxes:
                continue

            self.tracks.append({
                'bbox': (x1, y1, x2, y2),
                'id': self.new_track_id,
                'active': True,
                'old': 0,
                'age': 1,
            })

            boxes_track_id[box_index] = self.new_track_id
            boxes_is_new_track[box_index] = True
            self.new_track_id += 1

            self.log_info(f"Track is added. Number of tracks: {len(self.tracks)}")

        return boxes_track_id, boxes_is_new_track, boxes_ages

    def remove_old_tracks(self):
        remove_track_indexes = set()
        for track_index, track in enumerate(self.tracks):
            
            if track['old'] > self.old_threshold:
                remove_track_indexes.add(track_index)

        # Step 5: 시간 지난 track 삭제
        removed_ids = []
        removed_boxes = []
        removed_ages = []
        for track_index in sorted(remove_track_indexes, reverse=True):
            removed_ids.append(self.tracks[track_index]['id'])
            removed_boxes.append(self.tracks[track_index]['bbox'])
            removed_ages.append(self.tracks[track_index]['age'])
            del self.tracks[track_index]

        if removed_ids:
            self.log_info(f"Removed {len(removed_ids)} old tracks: {removed_ids}")
            return (
                np.array(removed_ids, dtype=int),
                np.array(removed_boxes, dtype=float),
                np.array(removed_ages, dtype=int)
            )
        else:
            return (
                np.zeros(0, dtype=int),
                np.zeros((0,4), dtype=float),
                np.zeros(0, dtype=int)
            )

    def _compute_iou(self, box1, box2):
        """Compute Intersection over Union (IoU) between two bounding boxes."""
        
        # xyxy
        x1_1, y1_1, x2_1, y2_1 = box1
        x1_2, y1_2, x2_2, y2_2 = box2
        
        # intersection
        ix1 = max(x1_1, x1_2)
        iy1 = max(y1_1, y1_2)
        ix2 = min(x2_1, x2_2)
        iy2 = min(y2_1, y2_2)
        
        # If there is no overlap
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        
        # Compute the intersection area
        intersection_area = (ix2 - ix1) * (iy2 - iy1)
        
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union_area = area1 + area2 - intersection_area
        
        # Compute IoU
        if union_area <= 0:
            return 0.0

        return intersection_area / union_area