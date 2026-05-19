// complex-test.js

class MathProcessor {
    constructor(numbers) {
        this.numbers = numbers;
    }

    // 类方法：包含 for 循环和 if-else 块
    process() {
        let result = [];
        for (let i = 0; i < this.numbers.length; i++) {
            const num = this.numbers[i];
            if (num % 2 === 0) {
                result.push(num * 2);
            } else if (num % 3 === 0) {
                result.push(num * 3);
            } else {
                result.push(num);
            }
        }
        return result;
    }
}

// 异步函数：包含 try-catch 块和 while 循环
async function fetchAndProcessData() {
    try {
        // 模拟异步请求
        const data = await new Promise((resolve) => {
            setTimeout(() => {
                resolve([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
            }, 300);
        });

        if (data && data.length > 0) {
            const processor = new MathProcessor(data);
            const processed = processor.process();
            
            let sum = 0;
            let index = 0;
            while (index < processed.length) {
                sum += processed[index];
                index++;
            }

            document.getElementById('output').innerText = `处理完成！计算结果总和为: ${sum}`;
        }
    } catch (error) {
        console.error("发生错误:", error);
    }
}

// 立即执行函数 (IIFE) 和闭包
(function initializeApp() {
    const appName = "Instrumentation Test App";
    
    // 箭头函数
    const showWelcome = () => {
        console.log(`Welcome to ${appName}`);
    };

    showWelcome();

    // DOM 事件监听器
    document.addEventListener('DOMContentLoaded', () => {
        const btn = document.getElementById('run-btn');
        if (btn) {
            btn.addEventListener('click', () => {
                document.getElementById('output').innerText = "处理中...";
                fetchAndProcessData().then(() => {
                    console.log("数据处理流程结束。");
                });
            });
        }
    });
})();