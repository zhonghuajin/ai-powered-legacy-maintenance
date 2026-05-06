package com.example.instrumentor;

import java.nio.file.Path;
import java.util.List;

public interface InstrumentationStep {

    /**
     * @param targets       目标文件/目录列表
     * @param context       共享上下文（传递 mapping 路径、incremental 标志等）
     * @return 处理的条目数量
     */
    int execute(List<Path> targets, PipelineContext context) throws Exception;

    String name();
}