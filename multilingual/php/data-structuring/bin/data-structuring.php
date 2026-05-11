#!/usr/bin/env php
<?php
declare(strict_types=1);

require __DIR__ . '/../vendor/autoload.php';

use App\Instrumentor\Data\Structuring\DataStructuring;

exit(DataStructuring::run($argv));