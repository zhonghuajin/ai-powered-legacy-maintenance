import React, { useState, useEffect } from 'react';

function createCounter(initialValue) {
    let count = initialValue;

    return function incrementCounter() {
        count++;
        if (count % 2 === 0) {
            console.log("Even count:", count);
        }
        return count;
    };
}

const counter = createCounter(10);
counter();

function complexParams(
    { a, b } = { a: 1, b: 2 },
    c = (() => {

        const temp = 100;
        return temp * 2;
    })(),
    ...rest
) {
    console.log("Complex params parsed", a, b, c, rest);
}

const complexObject = {
    value: 42,

    standardMethod() {
        console.log("Standard method");
    },

    async asyncMethod() {
        const res = await Promise.resolve(this.value);
        return res;
    },

    *generatorMethod() {
        yield this.value;
    },

    get doubleValue() {
        return this.value * 2;
    },

    set updateValue(newVal) {
        if (newVal > 0) {
            this.value = newVal;
        }
    }
};

function labelTest() {
    outerLoop: for (let i = 0; i < 3; i++) {
        innerLoop: for (let j = 0; j < 3; j++) {
            if (i === 1 && j === 1) {

                continue outerLoop;
            } else if (i === 2) {
                break outerLoop;
            }
            console.log(`i=${i}, j=${j}`);
        }
    }
}

function modernOperators(obj) {

    const val = obj?.prop ?? "default";
    let a = 1;
    a ||= 2;
    a &&= 3;

    if (val === "default") {
        console.log("Used default value");
    }
}

function silentFail() {
    try {
        throw new Error("Silent");
    } catch {

        console.log("Caught an error but ignored the error object");
    }
}

export function exportedFunction() {
    console.log("I am exported");
}

export default class DefaultExportedClass {
    constructor() {
        this.initialized = true;
    }

    init() {
        if (this.initialized) {
            console.log("Ready");
        }
    }
}

export const ComplexComponent = ({ items }) => {
    const [state, setState] = useState(null);

    useEffect(() => {
        let isMounted = true;

        async function fetchInitialData() {
            if (isMounted) {
                setState("Loaded");
            }
        }
        fetchInitialData();

        return () => {
            isMounted = false;
            console.log("Cleanup executed");
        };
    }, []);

    return (
        <div className="wrapper">
            {items.length > 0 ? (
                items.map(item => {

                    if (item.hidden) {
                        return null;
                    }
                    return (
                        <div key={item.id} onClick={(e) => {
                            e.preventDefault();
                            setState(item.value);
                        }}>
                            {item.name}
                        </div>
                    );
                })
            ) : (
                <p>No items found</p>
            )}
        </div>
    );
};

function loadModuleDynamically() {
    import('./some-module.js').then(module => {
        module.doSomething();
    }).catch(err => {
        console.error("Failed to load module");
    });
}