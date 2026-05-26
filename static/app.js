// 로컬 테스트 시에는 상대 경로를 사용하고, 외부 배포(Vercel 등) 시에는 .env에 설정된 ngrok 주소로 연결
const BACKEND_URL = window.location.origin.includes('localhost') || window.location.origin.includes('127.0.0.1')
    ? ''
    : 'https://seducing-issue-overflow.ngrok-free.dev';

document.addEventListener('DOMContentLoaded', () => {
    const onboardForm = document.getElementById('onboardForm');
    const submitBtn = document.getElementById('submitBtn');
    const btnText = submitBtn.querySelector('.btn-text');
    const btnLoader = submitBtn.querySelector('.btn-loader');

    const taskFileBox = document.getElementById('taskFileBox');
    const taskFileInput = document.getElementById('taskFile');
    const taskFileInfo = document.getElementById('taskFileInfo');

    const onboardFileBox = document.getElementById('onboardFileBox');
    const onboardFileInput = document.getElementById('onboardFile');
    const onboardFileInfo = document.getElementById('onboardFileInfo');

    const statusModal = document.getElementById('statusModal');
    const modalIcon = document.getElementById('modalIcon');
    const modalTitle = document.getElementById('modalTitle');
    const modalMessage = document.getElementById('modalMessage');
    const modalCloseBtn = document.getElementById('modalCloseBtn');

    // Drag and Drop Setup helper
    function setupDragAndDrop(box, input, infoDiv, defaultTitle) {
        // Trigger click on input
        box.addEventListener('click', () => input.click());

        // Update when file is selected
        input.addEventListener('change', () => {
            if (input.files.length > 0) {
                const file = input.files[0];
                infoDiv.textContent = `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
                box.style.borderColor = 'var(--accent-color)';
                box.style.background = 'rgba(16, 185, 129, 0.05)';
            } else {
                infoDiv.textContent = '';
                box.style.borderColor = '';
                box.style.background = '';
            }
        });

        // Drag events
        ['dragenter', 'dragover'].forEach(eventName => {
            box.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                box.classList.add('dragover');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            box.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
                box.classList.remove('dragover');
            }, false);
        });

        box.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files.length > 0 && files[0].type === 'application/pdf') {
                input.files = files;
                // Dispatch change event manually to trigger UI updates
                input.dispatchEvent(new Event('change'));
            } else {
                alert('PDF 파일만 업로드 가능합니다.');
            }
        });
    }

    setupDragAndDrop(taskFileBox, taskFileInput, taskFileInfo, '과업지시서 PDF');
    setupDragAndDrop(onboardFileBox, onboardFileInput, onboardFileInfo, '신입사원 온보딩 가이드 PDF');

    // Load Slack Channels
    const slackChannelSelect = document.getElementById('slackChannel');
    async function loadChannels() {
        try {
            // CORS OPTIONS 예비 요청을 허용하도록 백엔드를 세팅하고, 실제 헤더로 ngrok 우회
            const response = await fetch(`${BACKEND_URL}/slack/channels`, {
                headers: {
                    "ngrok-skip-browser-warning": "true"
                }
            });
            const data = await response.json();
            if (response.ok && data.status === 'success') {
                slackChannelSelect.innerHTML = '<option value="" disabled selected>대상 슬랙 채널을 선택하세요</option>';

                // 새로운 채널 생성 옵션 최상단 추가
                const newChanOption = document.createElement('option');
                newChanOption.value = '__NEW_CHANNEL__';
                newChanOption.textContent = '🆕 [새로운 전용 채널 자동 생성하여 진행]';
                slackChannelSelect.appendChild(newChanOption);

                data.channels.forEach(ch => {
                    const option = document.createElement('option');
                    option.value = ch.id;
                    option.textContent = `#${ch.name}`;
                    slackChannelSelect.appendChild(option);
                });
            } else {
                slackChannelSelect.innerHTML = '<option value="" disabled selected>슬랙 채널을 불러오지 못했습니다.</option>';
            }
        } catch (error) {
            console.error('Error fetching channels:', error);
            slackChannelSelect.innerHTML = '<option value="" disabled selected>채널 로드 중 네트워크 에러 발생</option>';
        }
    }
    loadChannels();

    const refreshChannelsBtn = document.getElementById('refreshChannelsBtn');
    if (refreshChannelsBtn) {
        refreshChannelsBtn.addEventListener('click', () => {
            slackChannelSelect.innerHTML = '<option value="" disabled selected>슬랙 채널 목록을 불러오는 중...</option>';
            loadChannels();
        });
    }

    // Form Submission
    onboardForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const nameVal = document.getElementById('workerName').value.trim();
        const emailVal = document.getElementById('workerEmail').value.trim();
        const channelIdVal = slackChannelSelect.value;

        // 1. 유효성 검사
        if (!nameVal || !emailVal || !channelIdVal) {
            alert('모든 근로자 정보 및 대상 슬랙 채널을 입력/선택해 주세요.');
            return;
        }

        if (taskFileInput.files.length === 0) {
            alert('과업지시서 PDF 파일을 선택하거나 드래그 앤 드롭으로 올려주세요.');
            return;
        }

        if (onboardFileInput.files.length === 0) {
            alert('신입사원 온보딩 가이드 PDF 파일을 선택하거나 드래그 앤 드롭으로 올려주세요.');
            return;
        }

        // Form Data Packaging
        const formData = new FormData();
        formData.append('name', nameVal);
        formData.append('email', emailVal);
        formData.append('channel_id', channelIdVal);

        if (taskFileInput.files.length > 0) {
            formData.append('task_description_pdf', taskFileInput.files[0]);
        }
        if (onboardFileInput.files.length > 0) {
            formData.append('onboarding_pdf', onboardFileInput.files[0]);
        }

        // UI Loading State
        submitBtn.disabled = true;
        btnText.textContent = '프로세스 기동 중...';
        btnLoader.hidden = false;

        try {
            const response = await fetch(`${BACKEND_URL}/onboard-web`, {
                method: 'POST',
                headers: {
                    "ngrok-skip-browser-warning": "true"
                },
                body: formData
            });

            const result = await response.json();

            if (response.ok && result.status === 'success') {
                showModal(false, '온보딩 시작 완료', result.message || '성공적으로 온보딩 프로세스를 기동하였습니다.');
                onboardForm.reset();
                taskFileInfo.textContent = '';
                onboardFileInfo.textContent = '';
                taskFileBox.style.borderColor = '';
                taskFileBox.style.background = '';
                onboardFileBox.style.borderColor = '';
                onboardFileBox.style.background = '';
            } else {
                showModal(true, '오류 발생', result.message || '온보딩 프로세스 시작 도중 오류가 발생했습니다.');
            }
        } catch (error) {
            console.error('Request failed:', error);
            showModal(true, '통신 오류', '서버와 통신하는 과정에서 예기치 않은 오류가 발생했습니다.');
        } finally {
            submitBtn.disabled = false;
            btnText.textContent = '온보딩 프로세스 가동';
            btnLoader.hidden = true;
        }
    });

    // Modal Control
    function showModal(isError, title, message) {
        modalTitle.textContent = title;
        modalMessage.textContent = message;
        if (isError) {
            modalIcon.textContent = '✕';
            modalIcon.className = 'modal-status-icon error';
        } else {
            modalIcon.textContent = '✓';
            modalIcon.className = 'modal-status-icon';
        }
        statusModal.hidden = false;
    }

    modalCloseBtn.addEventListener('click', () => {
        statusModal.hidden = true;
    });

    // Close on overlay click
    statusModal.addEventListener('click', (e) => {
        if (e.target === statusModal) {
            statusModal.hidden = true;
        }
    });
});