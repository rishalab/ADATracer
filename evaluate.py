import json
import argparse
import re
from pathlib import Path
from typing import Dict, List

def normalize_req_id(req_id: str) -> str:
    if not isinstance(req_id, str):
        return str(req_id)
    m = re.search(r"\d+", req_id)
    return m.group(0) if m else req_id

def normalize_path(p: str) -> str:
    if not isinstance(p, str):
        return ""
    return Path(p.replace("\\", "/")).as_posix().lower()


def paths_match(pred: str, gt: str) -> bool:
    pred = normalize_path(pred)
    gt = normalize_path(gt)
    return pred.endswith(gt) or gt.endswith(pred)

def load_ground_truth(path: str) -> Dict[str, List[str]]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    gt: Dict[str, List[str]] = {}
    for req, paths in raw.items():
        norm_req = normalize_req_id(req)
        gt[norm_req] = [normalize_path(p) for p in paths if isinstance(p, str)]
    return gt


def load_predictions(path: str) -> Dict[str, List[str]]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    preds: Dict[str, List[str]] = {}
    for req, items in raw.items():
        norm_req = normalize_req_id(req)
        paths: List[str] = []
        for item in items:
            if isinstance(item, str):
                paths.append(item)
            elif isinstance(item, dict):
                if "file_path" in item:
                    paths.append(item["file_path"])
                elif "file" in item:
                    paths.append(item["file"])
        preds[norm_req] = [normalize_path(p) for p in paths if p]
    return preds

def count_true_positives(predicted: List[str], truth: List[str]) -> int:
    matched_gt = set()
    for p in predicted:
        for g in truth:
            if paths_match(p, g):
                matched_gt.add(g)
    return len(matched_gt)


def precision_recall_f1(predicted: List[str], truth: List[str]):
    tp = count_true_positives(predicted, truth)
    fp = len(predicted) - tp
    fn = len(truth) - tp

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )

    return precision, recall, f1


def precision_at_k(predicted: List[str], truth: List[str], k: int) -> float:
    topk = predicted[:k]
    tp = count_true_positives(topk, truth)
    return tp / k if k > 0 else 0.0


def recall_at_k(predicted: List[str], truth: List[str], k: int) -> float:
    topk = predicted[:k]
    tp = count_true_positives(topk, truth)
    return tp / len(truth) if truth else 0.0

def evaluate(
    ground_truth: Dict[str, List[str]],
    predictions: Dict[str, List[str]],
    k: int,
):
    results = {}

    precisions = []
    recalls = []
    f1s = []
    precisions_at_k = []
    recalls_at_k = []
    for req in predictions.keys():
        gt_paths = ground_truth.get(req, [])
        pred_paths = predictions.get(req, [])
        precision, recall, f1 = precision_recall_f1(pred_paths, gt_paths)
        p_at_k = precision_at_k(pred_paths, gt_paths, k)
        r_at_k = recall_at_k(pred_paths, gt_paths, k)
        results[req] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            f"precision@{k}": p_at_k,
            f"recall@{k}": r_at_k,
            "ground_truth_count": len(gt_paths),
            "predicted_count": len(pred_paths),
        }
        precisions.append(precision)
        recalls.append(recall)
        f1s.append(f1)
        precisions_at_k.append(p_at_k)
        recalls_at_k.append(r_at_k)
    if precisions:
        results["__macro__"] = {
            "macro_precision": sum(precisions) / len(precisions),
            "macro_recall": sum(recalls) / len(recalls),
            "macro_f1": sum(f1s) / len(f1s),
            f"macro_precision@{k}": sum(precisions_at_k) / len(precisions_at_k),
            f"macro_recall@{k}": sum(recalls_at_k) / len(recalls_at_k),
        }

    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ground-truth", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output")
    args = parser.parse_args()
    gt = load_ground_truth(args.ground_truth)
    preds = load_predictions(args.predictions)
    results = evaluate(gt, preds, args.top_k)
    print("\nREQ   Prec   Rec    F1    P@K   R@K")
    print("-" * 60)
    for req, s in results.items():
        if req == "__macro__":
            continue
        print(
            f"{req:<4} "
            f"{s['precision']:.3f} "
            f"{s['recall']:.3f} "
            f"{s['f1']:.3f} "
            f"{s[f'precision@{args.top_k}']:.3f} "
            f"{s[f'recall@{args.top_k}']:.3f}"
        )
    if "__macro__" in results:
        m = results["__macro__"]
        print("-" * 60)
        print(
            f"MACR "
            f"{m['macro_precision']:.3f} "
            f"{m['macro_recall']:.3f} "
            f"{m['macro_f1']:.3f} "
            f"{m[f'macro_precision@{args.top_k}']:.3f} "
            f"{m[f'macro_recall@{args.top_k}']:.3f}"
        )
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\n[OK] Results written to {args.output}")


if __name__ == "__main__":
    main()