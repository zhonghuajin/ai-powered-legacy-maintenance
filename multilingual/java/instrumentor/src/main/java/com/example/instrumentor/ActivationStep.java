package com.example.instrumentor;

import java.nio.file.Path;
import java.util.List;

public class ActivationStep implements InstrumentationStep {

    @Override
    public String name() { return "Activation"; }

    @Override
    public int execute(List<Path> targets, PipelineContext context) throws Exception {
        InstrumentActivator activator = new InstrumentActivator();
        int total = 0;
        for (Path target : targets) {
            total += activator.activate(target);
        }
        return total;
    }
}