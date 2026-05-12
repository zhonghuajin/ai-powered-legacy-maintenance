<?php

namespace App\Instrumentation;

$localAutoload = dirname(__DIR__) . '/vendor/autoload.php';
if (file_exists($localAutoload)) {
    require_once $localAutoload;
}

class InstrumentLog {
    private static $redis = null;
    private static $pid = null;
    
    private static $buffer = [];
    private static $registered = false;
    private static $batchSize = 100;

    private static function getRedis() {
        if (self::$redis === null) {
            try {
                self::$redis = new \Predis\Client([
                    'scheme' => 'tcp',
                    'host'   => '127.0.0.1',
                    'port'   => 6379,
                ]);
            } catch (\Exception $e) {
                error_log("[InstrumentLog] Redis connection failed: " . $e->getMessage());
            }
        }
        return self::$redis;
    }

    private static function getPid() {
        if (self::$pid === null) {
            self::$pid = getmypid();
            $redis = self::getRedis();
            if ($redis) {
                $redis->rpush('instrumentor:pids_order', [self::$pid]);
            }
        }
        return self::$pid;
    }

    public static function staining($message) {
        if (!self::$registered) {
            register_shutdown_function([__CLASS__, 'flush']);
            self::$registered = true;
        }

        self::$buffer[] = $message;

        if (count(self::$buffer) >= self::$batchSize) {
            self::flush();
        }
    }

    public static function flush() {
        if (empty(self::$buffer)) {
            return;
        }

        $redis = self::getRedis();
        if ($redis) {
            $pid = self::getPid();
            $key = 'instrumentor:log:' . $pid;
            
            try {
                $redis->rpush($key, self::$buffer);
            } catch (\Exception $e) {
                error_log("[InstrumentLog] Redis flush failed: " . $e->getMessage());
            }
        }

        self::$buffer = [];
    }
}