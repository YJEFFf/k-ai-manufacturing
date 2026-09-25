// 웹 연결은 아직 미완료다. 검증된 실행 경로는 train.py / predict.py다.
// 다음 구현에서 serve.py의 /api/overview, /api/analyze에 연결한다.
document.getElementById('message').textContent = '웹 시연 화면은 구현 중입니다. 현재 검증된 실행 경로는 train.py / predict.py입니다.';
document.querySelectorAll('button, select, input').forEach(element => { element.disabled = true; });
